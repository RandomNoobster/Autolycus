# About Autolycus

Autolycus is an open source bot for finding raid targets in PnW. It was initially developed for in-house usage, but I decided to make it public. As far as I am aware, no other public bots have extensive raid finding functionality. The lack of such functionality is what motivated me to make this public. Nonetheless, the fact that it was originally meant for in-house usage means multiple things. Firstly, it means that the code isn't pretty. Secondly, it means that it's not designed to be easy to self-host. 

## Self hosting

It it designed to be run on [replit.com](https://replit.com). You can simply fork the [repl](https://replit.com/@PoliticsAndWar/Autolycus). For it to function, you will need to add the required environment variables. A tutorial about environment variables on replit can be found [here](https://docs.replit.com/programming-ide/storing-sensitive-information-environment-variables). The following variables are required:
- `api_key` (your pnw api key)
- `bot_token` (your discord bot key)
- `pymongolink` (the [connection string](https://docs.mongodb.com/manual/reference/connection-string/) to your mongoDB)
- `version` (the name of the database in your mongoDB collection)
- `ip` (the ip you want the flask server to run on. Use 127.0.0.1 for localhost, or 0.0.0.0 if you are on replit)
- `debug_channel` (the id of the channel you want the bot to send error messages in)

You will also need a mongoDB database. A guide on how to set one up, can be found [here](https://docs.atlas.mongodb.com/getting-started/). If you are unable to set up a database, it might be wise to avoid self-hosting.
In addition to the database, you will need to fork this [repl](https://replit.com/@PoliticsAndWar/Autolycus-database-updater). For this one you need the following environment variables:
- `api_key` (your pnw api key)
- `pymongolink` (the [connection string](https://docs.mongodb.com/manual/reference/connection-string/) to your mongoDB)
- `version` (the name of the database in your mongoDB collection)
- `ip` (the ip you want the flask server to run on. Use 127.0.0.1 for localhost, or 0.0.0.0 if you are on replit)
