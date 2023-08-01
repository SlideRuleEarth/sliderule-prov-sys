# Sliderule Provisioning System (PS)

A system to provision and manage multiple organizations, clusters and users
using [sliderule-ps-web](https://github.com/ICESat2-SlideRule/sliderule-ps-web) as the front end website and [sliderule-ps-server](https://github.com/ICESat2-SlideRule/sliderule-ps-server) as a backend terraform command line interface proxy 

Detailed [documentation](http://icesat2sliderule.org/rtd/) on installing and using this project can be found at [icesat2sliderule.org](http://icesat2sliderule.org).

## I. Building the Provisioning System (PS) development environment:

The SlideRule **provisioning system** is built and run locally for development purposes using [Docker](https://docs.docker.com/).  

### Prerequisites

This guide makes the following assumptions:

- you have docker installed and running with [Docker BUILDKIT](https://docs.docker.com/build/buildkit/).
- you have an amazon credentials file with a valid key as default profile OR You have those values set as environment variables
- For deployment to amazon, your amazon credentials have at least the privileges needed to deploy your system's sliderule cluster

Docker containers encapsulate the python the environment.
Create a local virtual python environment that mirrors what is used inside the docker container. This allows your local IDE (i.e. vscode or equivalent) to resolve library imports that matches the docker environment. This is ***not strictly neccessary*** but allows one to take advantage of the IDE codesense features:

e.g. [native python venv](https://docs.python.org/3/library/venv.html)
<pre>
$ python3 -m your_env .venv
$ source .venv/bin/activate
$ pip install -r docker/ps-web/requirements.txt       
</pre>
 OR [miniconda](https://docs.conda.io/en/latest/miniconda.html)
 <pre>
conda create --name your_env python
source activate your_env
</pre>
Create local repositories for both the microservices server (i.e. ps-server) and the web server (ps-web)

<pre>$ git clone git@github.com:ICESat2-SlideRule/sliderule-ps-server.git
$ git clone git@github.com:ICESat2-SlideRule/sliderule-ps-web.git</pre>

### Create a sliderule-ps-web development environment file (these have secrets so do NOT check into repo, i.e. these are in .gitignore)

- sliderule-ps-web/.env.dev

(use appropriate vals for your enviroment)

Here is an example using the necessary/expected env variables:

<pre>
DEBUG=TRUE
DJANGO_SECRET_KEY=[put a sufficiently long secret string here]
JWT_SECRET_KEY=[put a sufficiently long secret string here]
DJANGO_ALLOWED_HOSTS=localhost 127.0.0.1 [::1] 0.0.0.0 ps-web ps-db ps-nginx
POSTGRES_DB=ps_postgres_db
POSTGRES_USER=ps_admin
POSTGRES_PASSWORD=[put a sufficiently long secret string here]
POSTGRES_PASSWORD_=[put a sufficiently long secret string here]
SQL_ENGINE=django.db.backends.postgresql
SQL_HOST=ps-db
SQL_PORT=5432
GRPC_POLL_STRATEGY: poll
DOMAIN=[your_domain e.g. mydomain.org]
</pre>

### Create the PS development docker network (**one time only** - unless pruned by docker prune command)

<pre>$ docker network create ps_network</pre>

Build the sliderule-ps-server (NOTE: the protobuf file that describes the interface between ps-server and ps-web is checked in at ps-server. So ps-server is built before ps-web)

<pre>$ cd ../sliderule-ps-server
$ make docker</pre>

build the sliderule-web-server

<pre>$ cd ../sliderule-ps-web 
$ make docker
</pre>

### Start the PS development docker network

<pre>$ make network</pre>

### Start the sliderule-ps-web server

***from sliderule-ps-web directory*** run:

<pre>make run</pre>

Look for this:

<pre>
 ⠿ Container ps-db     Created   0.1s
 ⠿ Container redis  Created   0.0s
 ⠿ Container ps-web    Created   0.0s
 ⠿ Container ps-nginx  Created   0.1s
Attaching to ps-db, ps-nginx, redis, ps-web
.
.
.
... then all the log messages from the startup of those containers...</pre>
NOTE: The development environment uses a docker volume for the postgres database. The very first time you will see something like the following (which is the schema initialization implemented via Django migrations):
<pre>

</pre>

### Start the sliderule-ps-server server

***from sliderule-ps-server*** directory run:

<pre>make run</pre>

Look for something like this

<pre>[2022-04-08:11:15:48] [INFO] [ps_server.py:1131:main] [

------------------- Server is READY listening on port :50051 ----------------

]</pre>


#

## Test the local dev website

Open a browser and enter this url:

[http://localhost/](http://localhost/)


### To stop either PS service. In it's directory run:

<pre>$  make down</pre>

## II. PS development how-tos

### Use 'Make help':
<pre>
$ make help
#----------------------------------------------------------------------------------------- 
# Makefile Help                
#----------------------------------------------------------------------------------------- 
#----target--------------------description------------------------------------------------ 
docker-prune                   clean up all docker images and volumes
down                           bring down the ps-server and all the ancillary containers
help                           That's me!
network                        One time set up of docker development network(this is persistent)
docker         build the container using cache and tag it with $(PS_SERVER_DOCKER_TAG) 
docker-no-cache  build the container using cache and tag it with $(PS_SERVER_DOCKER_TAG) 
run                            run the docker ps-server service:  docker-compose run --name ps-server ps-server 
</pre>

### Build/Rebuild the image from scratch

<pre>$ make docker-no-cache</pre>

### Execute shell command in local container

<pre>$ docker exec -it ps-web &ltcmd&gt  
e.g. docker exec -it ps-web ls -altr</pre>

### Execute Django manage.py cmd in local container

<pre>$ docker exec -it ps-web python manage.py &ltcmd&gt  
e.g. docker exec -it ps-web python manage.py help</pre>


### Procedure for clearing/resetting migrations in the development DB

(i.e. in development for testing and creating a development DB from scratch)

Migration operations are done in a way so that the migration files can be captured for checking into the repository.

1. From the host terminal from the project directory clean migrations like this:<pre>$ find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
$ find . -path "*/migrations/*.pyc"  -delete</pre>
2. Remove the postgres db by deleting the docker volume which is called 'sliderule-ps-web_postgres_data'<pre>$ docker volume rm prov-sys_postgres_data</pre>

3. make run (the entrypoint.sh file will execute and run the migrations)<pre>make run</pre>

4. Create required static entries for Granularity choices table: 
Use <pre>python manage.py makemigrations --empty users</pre> to create an empty migration file that has the right location and name for migrations to then add code to populate the initial static data tables for django app 'users'


5.  Edit the file you just created in the previous step.This will create the initial table GranChoice table with HOURLY DAILY MONTHLY
The file you edit should look like this:
<pre><code>
    from django.db import migrations


    def populate_gran_choice(apps,  schema_editor):
        GranChoice = apps.get_model('users', 'GranChoice')
        h = GranChoice.objects.create(granularity='HOURLY')
        h.save()
        d = GranChoice.objects.create(granularity='DAILY')
        d.save()
        m = GranChoice.objects.create(granularity='MONTHLY')
        m.save()

    class Migration(migrations.Migration):

        dependencies = [
            ('users', '0001_initial'),
        ]

        operations = [
         migrations.RunPython(populate_gran_choice)
        ]
</code></pre>
more details on manual migrations are here https://docs.djangoproject.com/en/4.1/topics/migrations/#data-migrations 

6. Now run the migrate command again to populate the table like this:<pre>
$ docker exec -it prov-sys-ps-web python manage.py migrate</pre>
7. Initialize the database as described in the next section

### One-time Initialization of the database
The following must be done when creating a new database or resetting/clearing a development database(i.e. when the docker volume was deleted). This creates a superuser (admin) and a group for privileged users (PS_Developer)

1. From a host terminal add a superuser like this:<pre>$ docker exec -it prov-sys-ps-web python manage.py createsuperuser --username admin --email [your admin email address]</pre>
-- OR --  from a shell in the container like this:<pre>
python manage.py createsuperuser --username admin --email [your admin email address]</pre>

2. In a browser go to admin site (i.e. http://localhost/admin) and sign in a the admin superuser. Create a group for permissions using the Django admin site signed in as the superuser. Call it "PS_Developer". give it the privileges by selecting them to highlight those that are to be added, click the arrow to add the highlighted privileges. Select these: 
    * all the users: entries (except ones begining with users | user)
    * all token_blacklist
    * all django_* (i.e. all that begin with django_)
<pre>
* users | [table] <add/change/delete/view> 
</pre>

You can go back and add or delete privileges as needed.

3. in a browser go to [http://localhost/register](http://localhost/register) for the developement system or [https:{domain}/register]() for the deployed system and sign up a new developer (i.e. have the developer create their basic user account)

4. in a browser go to [http://localhost/admin](http://localhost/admin) or the deployed equivalent and login as the admin user to be able to add privileges for the developer by giving the new developer user created in the previous step PS_Developer group privileges as follows:

- select "Users". Then for each developer that should have access to the admin site, select that user then click 'Staff status' (NOTE: NOT superuser!)
- select "Users". Then for each developer that should have PS_Developer elevated privileges, select that user. Then for Groups select 'Staff status' to highlight it. Then hit the save button

5. in a browser login as the Developer user (have the developer login)

- go to site (should default to /browse) in a PS_Developer privileged account and from /browse click the "Add New Organization Account" button and add the organization 'Developers' (or any other needed) NOTE: This button is only displayed for logged in users that have "Staff status" selected and PS_Developer group privileges

### Backup development DB:

<pre>docker exec ps-db /bin/bash -c "/usr/bin/pg_dump -U ps_admin ps_postgres_db" | gzip -9 > sliderule-postgres-backup$(date +%Y-%m-%d_%H_%M_%S).sql.gz</pre>

### Restore development DB:

<pre>gunzip < sliderule-postgres-backup[date_portion_of_name].sql.gz | docker exec -i ps-db psql -U ps_admin -d ps_postgres_db </pre>

### Interactive shell to ps project's Django models (i.e. ORM)

<pre>$ docker exec -it ps-web python manage.py shell </pre>

Use this instead of simply typing “python”, because manage.py sets the DJANGO_SETTINGS_MODULE environment variable, which gives Django the Python import path to ps/settings.py file. The database ORM API is documented here: [Django ORM](https://docs.djangoproject.com/en/4.1/topics/db/queries/)

### Run postgres CLI (use correct values for username and db name)

<pre>$ docker run -it --rm --network ps_network postgres psql -h ps-db -U ps_admin
you will get a prompt like this 
postgres=#

try:
\c ps_postgres_db   (to connect to our db)
\l
\q
\dt
</pre>

### Interactive bash shell to container without running the web server

<pre> docker-compose run --name ps-web ps-web bash</pre>

### NGINX config hints. NOTE:it is possible that nginx config is scattered in many files. To get complete current active config use:

<pre>$ docker-compose exec nginx nginx -T </pre>

### URLS
Users can access the system making provisioning capcacity requests programattically with the RESTful api.
[RESTFul API URLs are documented here](https://slideruleearth.io/rtd/user_guide/prov-sys.html)

### How-To create a new organization

1. Have the person who will be the organization owner create a user account
2. Have a user who is designated 'staff' got to browse and click add new organization

