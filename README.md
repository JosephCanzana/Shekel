# Shekel

## First clone & docker update

1. Create .env file

2. put the output of this key in flask secret key
> python3 -c "import secrets; print(secrets.token_hex(24))"

3. Install all required pip in local to make up for slow internet
> pip download -r requirements.txt -d ./pip_packages --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:

4. Build and run the docker
> docker compose up --build

## Running the app
1. docker compose up

