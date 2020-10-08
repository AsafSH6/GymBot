
<!--
*** Thanks for checking out this README Template. If you have a suggestion that would
*** make this better, please fork the repo and create a pull request or simply open
*** an issue with the tag "enhancement".
*** Thanks again! Now go create something AMAZING! :D
***
***
***
*** To avoid retyping too much info. Do a search and replace for the following:
*** AsafSH6, GymBot, twitter_handle, email
-->





<!-- PROJECT SHIELDS -->
<!--
*** I'm using markdown "reference style" links for readability.
*** Reference links are enclosed in brackets [ ] instead of parentheses ( ).
*** See the bottom of this document for the declaration of the reference variables
*** for contributors-url, forks-url, etc. This is an optional, concise syntax you may use.
*** https://www.markdownguide.org/basic-syntax/#reference-style-links
-->

<!-- PROJECT LOGO -->
<h1 align="center">GymBot</h>
<br />
<p align="center">
  <h3 align="center">Telegram Gym Bot</h3>

  <p align="center">
    <i>Telegram bot to forgroups which want to help each other keep the motivation</i>
    <br />
    <br />
    <a href="https://github.com/AsafSH6/GymBot/issues">Report Bug</a>
    ·
    <a href="https://github.com/AsafSH6/GymBot/issues">Request Feature</a>
  </p>
</p>



<!-- TABLE OF CONTENTS -->
## Table of Contents

* [Built With](#built-with)
* [Getting Started](#getting-started)
  * [Prerequisites](#prerequisites)
  * [Installation](#installation)
* [Usage](#usage)
* [Contact](#contact)





### Built With

* []()Python 2.7
* []()MongoDB


<!-- GETTING STARTED -->
## Getting Started

To get a local copy up and running follow these simple steps.

### Prerequisites

Telegram bot token
</br>

1.  Download the Telegram app to your phone
2.  Create telegram bot
```sh
https://core.telegram.org/bots#creating-a-new-bot
```
> **when finishing to create the bot its important to save his token.** 

MongoDB
<br />
* Set up MongoDB database (there is free options that would fit development).
<br />
if needed you can use this guide for the set up
```sh
https://docs.atlas.mongodb.com/getting-started/
```
>**when finishing to set up the MongoDB its important to save the connection string.**

### Installation

1. Clone the repo
```sh
git clone https://github.com/AsafSH6/GymBot.git
```
2. Enter the project directory
```sh
cd ./GymBot
``` 
2. Install dependencies
```sh
pip install -r requirements.txt
```
3. Setup environment variables
```sh
export BOT_TOKEN=<telegram_bot_token>
export MONGODB_URL_CON=<MongoDB_connection_string>
``` 



<!-- USAGE EXAMPLES -->
## Usage

* To start the server you need to run the follwing command.
```sh
python gym_bot_app/gym_bot.py
```
* To start using the bot
```sh
1. Create telegram group with your friends
2. Add GymiousBot to the group
3. Use the bot commands set to start
```



## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request




<!-- CONTACT -->
## Contact

- email: asafsemail@gmail.com

- Project Link: [https://github.com/AsafSH6/GymBot](https://github.com/AsafSH6/GymBot)

