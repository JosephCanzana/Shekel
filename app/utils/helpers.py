from flask import render_template

def message(num=400, message="Error occur"):
    return render_template("message.html", message=message, error_code=num)