import razorpay


class FlaskRazorPay(razorpay.Client):
    key = "rzp_test_SnOiB7Tz90f9UR"
    secret = "MC8UJ6TXqUNaHHHpng4PmXuG"

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

        super(FlaskRazorPay, self).__init__(auth=(self.key, self.secret))

    def init_app(self, app=None):
        self.key = "rzp_test_SnOiB7Tz90f9UR" # app.config.get('RAZOR_PAY_KEY', None)
        self.secret = "MC8UJ6TXqUNaHHHpng4PmXuG" #app.config.get('RAZOR_PAY_SECRET', None)
        

razor = FlaskRazorPay()
