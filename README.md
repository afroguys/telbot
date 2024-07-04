sudo apt-get update

sudo apt-get upgrade -y

sudo apt-get install python3 python3-pip qbittorrent-nox -y

sudo apt-get install qbittorrent-nox -y

#Start qBittorrent in the background:

qbittorrent-nox -d

pip3 install python-telegram-bot qbittorrent-api

############################################################

Step 5: Set Up qBittorrent Web UI

By default, qBittorrent Web UI runs on http://localhost:8080 with default credentials:

Username: admin

Password: adminadmin

You should change these credentials for security purposes:

Open the Web UI in a browser or using a tool like curl.

Change the default password.

#############################################################
