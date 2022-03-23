from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def main():
    return "It lives!!"

def run():
    Thread(target=lambda: app.run(host="0.0.0.0", port=5000)).start()