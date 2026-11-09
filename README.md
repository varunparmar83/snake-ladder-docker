SNAKE AND LADDER GAME - HOW TO RUN (WITH DOCKER)
=================================================

Requirement: Docker Desktop must be installed and running
(wait until it shows "Engine running").
Download: https://www.docker.com/products/docker-desktop


OPTION 1: RUN FROM DOCKER HUB (FASTEST, NO CODE NEEDED)
-------------------------------------------------------
1. Open a terminal (Git Bash, CMD or PowerShell).

2. Run this command:

   docker run -d --name snake-ladder -p 8080:80 ustad001/snake-ladder:latest

3. Open your browser and go to:

   http://localhost:8080


OPTION 2: BUILD FROM THE GITHUB REPO
------------------------------------
1. Clone the project:

   git clone https://github.com/varunparmar83/snake-ladder-docker.git
   cd snake-ladder-docker

2. Build the Docker image:

   docker build -t snake-ladder .

3. Run the container:

   docker run -d --name snake-ladder -p 8080:80 snake-ladder

4. Open your browser and go to:

   http://localhost:8080


OPTION 3: WITHOUT DOCKER
------------------------
1. Clone the project (same as Option 2, step 1).

2. Open index.html in your browser.

   If audio or scripts do not work, start a small local server:

   python -m http.server 8000

   Then open: http://localhost:8000


USEFUL COMMANDS
---------------
See running containers:   docker ps
See logs:                 docker logs snake-ladder
Stop the game:            docker stop snake-ladder
Remove the container:     docker rm snake-ladder


COMMON PROBLEMS
---------------
- "port is already allocated"
  Use another port, for example: -p 8081:80  and open http://localhost:8081

- "cannot connect to the Docker daemon" or "failed to connect to the docker API"
  Docker Desktop is not running. Start it and wait for "Engine running".

- "container name is already in use"
  Run: docker rm -f snake-ladder   and then run the docker run command again.

- Play from another device on the same Wi-Fi
  Find your PC IP with: ipconfig
  Then open http://YOUR-PC-IP:8080 on the other device
  (allow the port in Windows Firewall if needed).