# Shekel

## App link
- Production
> https://proto.taild735b3.ts.net
- Demo
> https://proto.taild735b3.ts.net:8443

## First clone & docker update

1. Create .env file

2. put the output of this key in flask secret key
> python3 -c "import secrets; print(secrets.token_hex(24))"

3. Install all required pip in local to make up for slow internet
> pip download -r requirements.txt -d ./pip_packages --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:

4. Build and run the docker
> docker compose up --build

## MIGRATIONS
1. make the migration (auto-detects your model changes)
>flask db migrate -m "your comment"

2. apply it to the database
>flask db upgrade

## DOCKER
1. Run command
> docker compose up
2. View Containers details
> docker ps
3. Access mysql
> docker compose exec db mysql -u root -p
4. Access container os
> docker exec -it shekel-web-1 bash
5. Production build
> docker compose -f docker-compose.prod.yml up -d --build
6. Demo build
> docker compose -f docker-compose.demo.yml up -d --build

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

## Mysql
1. schema
> mysqldump -u username -p --no-data db_name > schema.sql

## Tailscale
1. funnel
> tailscale funnel 80
2. expose demo
> tailscale serve --bg --https=8443 http://localhost:8080

## Nginx
1. reload nginx
> docker compose up -d --force-recreate nginx