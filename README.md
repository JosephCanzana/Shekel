# Shekel

## First clone & docker update

1. Create .env file

2. put the output of this key in flask secret key
> python3 -c "import secrets; print(secrets.token_hex(24))"

3. Install all required pip in local to make up for slow internet
> pip download -r requirements.txt -d ./pip_packages --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:

4. Build and run the docker
> docker compose up --build

## DOCKER
1. Run command
> docker compose up
2. View Containers details
> docker ps

## Tailwind
1. Install Tailwind
> npm install -D @tailwindcss/cli
2. Verify Installation
> ls node_modules/.bin/ | grep tailwind

## Alpinejs
1. Install Alpinejs
> npm install alpinejs
2. Verify Installation
> ls node_modules | grep alpinejs