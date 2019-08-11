from flask_security import current_user
from sqlalchemy import and_

from src import db, razor as razorpay, sms
from src.user.models import UserToUser
from src.utils import ModelResource, operators as ops
from src.utils.celery import celery
from .schemas import Due, DueSchema, Payment, PaymentSchema

''' Celery Tasks '''
    
# Send reminder on due-date
@celery.task(name="celery.sms_on_due_date")
def sms_on_due_date(dueObj):
    # Only execute if payment is not done
    if dueObj.due_date is not None:

        content= [dict(
        message=f'3 days remaining of your {dueObj.creator.business_name} subscription! Pay now.',
        to=[dueObj.customer.mobile_number]
        )]

        sms.send_sms(content=content)

# Send reminder 3 dasy before due-date
@celery.task(name="celery.sms_before_3_days")
def sms_before_3_days(dueObj):
    content= [dict(
        message=f'Failure to pay today will result in halt of your {dueObj.creator.business_name} service! Pay Now!',
        to=[dueObj.customer.mobile_number]
        )]

    sms.send_sms(content=content)

    # dueObj.due_date = None if payment is successful

@celery.task(name="celery.send_invoice")
def send_invoice(invoice, dueObj):
    content = [dict(message=f'Thank you for your interest in the service provided by'
            f' {dueObj.creator.business_name}. Here\'s your invoice and enjoy the service.\n'
            f' Invoice --> \n {invoice}', to=[dueObj.customer.mobile_number])]
            
    sms.send_sms(content=content)

@celery.task(name="celery.do_payment")
def do_payment(obj):
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
        return subscription

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
        return inv

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

    def after_objects_save(self, objects):
        for obj in objects:
            current_user.counter += 1
            obj.invoice_num = current_user.counter

            try:
                invoice = do_payment.delay(obj).result()
                send_invoice.delay(invoice, obj)
                if obj.transaction_type == 'subscription':
                    from datetime import timedelta
                    sms_queue.apply_async(args=[obj], eta=obj.due_date-timedelta(days=3))
                    sms_on_due_date.apply_async(args=[obj], eta=obj.due_date)
                elif obj.transaction_type == 'fixed':
                    obj.due_date = None 

            except Exception as e:
                print("Couldn't complete transaction:", e)

            db.session.commit()


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
