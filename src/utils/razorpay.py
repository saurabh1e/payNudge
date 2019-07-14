import razorpay


class FlaskRazorPay(razorpay.Client):
    key = None
    secret = None

    def init_app(self, app=None):
        self.key = app.config.get('RAZOR_PAY_KEY', None)
        self.secret = app.config.get('RAZOR_PAY_SECRET', None)

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

        super(FlaskRazorPay, self).__init__(auth=(self.key, self.secret))


razor = FlaskRazorPay()
