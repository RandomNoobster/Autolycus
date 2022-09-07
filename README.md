# About Autolycus

Autolycus is an open source bot for finding raid targets in PnW. It was initially developed for in-house usage, but I decided to make it public. As far as I am aware, no other public bots have extensive raid finding functionality. The lack of such functionality is what motivated me to make this public. Nonetheless, the fact that it was originally meant for in-house usage means multiple things. Firstly, it means that the code isn't pretty. Secondly, it means that it's not designed to be easy to self-host. 

## Self hosting

This particular branch is designed to be run on an Oracle-Linux system as can be found on their [cloud hosting service](https://cloud.oracle.com/).

In `/home/opc/Autolycus`, you need a .env file with the following environment variables:
- `api_key` (your pnw api key)
- `bot_token` (your discord bot key)
- `pymongolink` (the [connection string](https://docs.mongodb.com/manual/reference/connection-string/) to your mongoDB)
- `version` (the name of the database in your mongoDB collection)
- `ip` (the ip you want the flask server to run on. Use 127.0.0.1 for localhost, or 0.0.0.0 if you are on replit)
- `debug_channel` (the id of the channel you want the bot to send error messages in)


You also need to create this file: `/etc/systemd/system/autolycus.service`
```
[Unit]
Description=run bootup script

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/Autolycus
ExecStart=/usr/local/bin/bootup.sh

[Install]
WantedBy=multi-user.target
```


And this file: `/usr/local/bin/bootup.sh`
```
#!/bin/bash
cd /home/opc/Autolycus
while true; do
    pkill -9 python
    sudo git pull origin oracle
    pip3 install -r requirements.txt --user
    python3 main.py &
    sleep 86400
done
```


You will also need a mongoDB database. A guide on how to set one up, can be found [here](https://docs.atlas.mongodb.com/getting-started/). In addition to the database, you will need to fork this [repl](https://replit.com/@PoliticsAndWar/Autolycus-database-updater). For this one you need the following environment variables:
- `api_key` (your pnw api key)
- `pymongolink` (the [connection string](https://docs.mongodb.com/manual/reference/connection-string/) to your mongoDB)
- `version` (the name of the database in your mongoDB collection)
- `ip` (the ip you want the flask server to run on. Use 127.0.0.1 for localhost, or 0.0.0.0 if you are on replit)


### Helpful commands:
- `sudo -i` - get root privileges
- `exit` - exit root privileges
- `systemctl daemon-reload` - reload daemons
- `systemctl start autolycus` - start autolycus service
- `systemctl status autolycus` - get status of autolycus service
- `systemctl enable autolycus` - enable autolycus service to run at bootup
- `cat << EOF > PATH/file` - write to file
- `chmod u+x PATH/file.sh` - make bash file runnable
- `sudo chown opc:root PATH` - modify ownership of directory
- `sudo firewall-cmd --permanent --zone=public --add-service=http` - create firewall rules to allow access to the ports on which the HTTP server listens
- `firewall-cmd --zone=public --add-port=5000/tcp --permanent` - create firewall rule to allow access to port 5000
- `sudo firewall-cmd --reload` - reload firewall


### Helpful links:
- https://medium.com/@benmorel/creating-a-linux-service-with-systemd-611b5c8b91d6
- https://docs.oracle.com/en/learn/use_systemd/index.html#work-with-systemd-timer-units
- https://docs.oracle.com/en/learn/lab_compute_instance/index.html 
- https://www.youtube.com/watch?v=Jj9SscHb5ZQ