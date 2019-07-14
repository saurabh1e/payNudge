from flask_security import current_user
from sqlalchemy import and_

from src import db, razor as razorpay, sms
from src.user.models import UserToUser
from src.utils import ModelResource, operators as ops
from .schemas import Due, DueSchema, Payment, PaymentSchema


class DueResource(ModelResource):
    model = Due
    schema = DueSchema

    auth_required = True

    # roles_accepted = ('admin', 'business_owner', 'customer')

    exclude = ()

    filters = {
        'id': [ops.Equal, ops.In],
        'creator_id': [ops.Equal, ops.In],
        'customer_id': [ops.Equal, ops.In],
        'transaction_type': [ops.Equal, ops.In],
        'created_on': [ops.DateTimeEqual, ops.DateTimeLesserEqual, ops.DateTimeGreaterEqual],
        'due_date': [ops.DateTimeEqual, ops.DateTimeLesserEqual, ops.DateTimeGreaterEqual],
        'is_paid': [ops.Boolean],
        'is_cancelled': [ops.Boolean]

    }

    order_by = ['created_on', 'id', 'due_date']

    only = ()

    def has_read_permission(self, qs):
        return qs.filter(Due.creator_id == current_user.id)

    def has_change_permission(self, obj):

        if obj.creator_id == current_user.id and \
                db.session.query(UserToUser.query.filter(UserToUser.business_owner_id == current_user,
                                                         UserToUser.customer_id == obj.customer_id).exists()) \
                        .scalar():
            return True
        return False

    def has_delete_permission(self, obj):
        return False

    def has_add_permission(self, objects):
        for obj in objects:
            obj.creator_id = current_user.id
            if not db.session.query(UserToUser.query.filter(UserToUser.business_owner_id == current_user.id,
                                                            UserToUser.customer_id == obj.customer_id).exists()) \
                    .scalar():
                return False
        return True

    def after_objects_save(self, objects) -> None:
        for obj in objects:
            if obj.customer.razor_pay_id:

                customer = razorpay.customer.fetch(customer_id=obj.customer.razor_pay_id)
            else:
                customer = razorpay.customer.create(
                    data={'name': obj.customer.first_name, 'contact': obj.customer.mobile_number})
                obj.customer.razor_pay_id = customer['id']
                db.session.commit()
            print(customer)

            if obj.transaction_type == 'subscription':
                plan = razorpay.plan.create(data={
                    "period": "monthly",
                    "interval": 1,
                    "item": {
                        "name": obj.name,
                        "description": obj.name,
                        "amount": float(obj.amount) * 100,
                        "currency": "INR"
                    }
                })
                import time
                timestamp = time.mktime(obj.due_date.timetuple())
                data = dict(plan_id=plan['id'], total_count=obj.months, customer_notify=1, customer_id=customer['id'],
                            start_at=timestamp)
                subscription = razorpay.subscription.create(data=data)
                obj.razor_pay_id = subscription['id']
                db.session.commit()
                print(subscription)
                content = [dict(message=f'Thank you for your interest in the service provided by'
                f' {obj.creator.business_name}.Please complete your subscription and enjoy the service.'
                f' Click to pay--> {subscription["short_url"]}', to=[obj.customer.mobile_number])]
                sms.send_sms(content=content)

            else:
                inv = razorpay.invoice.create(data={
                    "customer": {
                        "name": obj.customer.first_name,
                        "email": "",
                        "contact": obj.customer.mobile_number
                    },
                    "type": "link",
                    "view_less": 1,
                    "amount": float(obj.amount) * 100,
                    "currency": "INR",
                    "description": obj.name,
                })
                print(inv)


class PaymentResource(ModelResource):
    model = Payment
    schema = PaymentSchema

    auth_required = True

    exclude = ()

    filters = {
        'id': [ops.Equal, ops.In],
        'razorpay_id': [ops.Equal, ops.In],
        'due_id': [ops.Equal, ops.In],
        'created_on': [ops.DateTimeEqual, ops.DateTimeLesserEqual, ops.DateTimeGreaterEqual],
    }

    order_by = ['created_on', 'id', 'due_id']

    only = ()

    def has_read_permission(self, qs):
        return qs.join(Due, and_(Due.id == Payment.due_id)).filter(Due.creator_id == current_user.id)

    def has_change_permission(self, obj):
        return False

    def has_delete_permission(self, obj):
        return False

    def has_add_permission(self, objects):
        return False
