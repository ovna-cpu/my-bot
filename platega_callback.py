from flask import request

@app.route('/platega_callback', methods=['POST'])
def platega_callback():
    return "OK", 200
