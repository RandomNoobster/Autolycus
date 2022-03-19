from flask import Flask
from threading import Thread
import os
ip = os.getenv("ip")

app = Flask('')

@app.route('/')
def main():
    return "It lives!!"

def run():
    app.run(host=ip, port=5000)    