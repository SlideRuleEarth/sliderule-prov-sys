# Database development notes
The prov-sys uses AWS RDS with Postgresql for the database.

## External backup of AWS RDS postgresql
AWS RDS is normally configured as not publicly accessible and it is configured to do AWS RDS system backups. However at times one might need to create a postgresql backup that can be used in development.
1) using the AWS console go to the RDS service and select the DB you want to backup. They are named based on domain. Then select Modify and under Connectivity, additioinal configuration make this db publicly accessable by selecting the checkbox that says public access


NOTE: DO NOT leave the RDS in this state! It is vulnerable to attack so only set this public for the amount of time it takes to back it up

2) using the AWS console change the security group for the \<domain\>-ps-rds-sg security group. Add an inbound rule for port 5432 protocol custom TCP and for source select "my-ip" to use your local IP address

3) using the AWS console update the security group for the ecs-web load balancer for the desired domain (e.g. testsliderule-ps-web-lb-sg) by adding an inbound rule with traffic type PostgreSQL and source as your IP port 5432

4) add route to private route table \<domain\>-ps-prv-rt with destination as your ip address and target as the internet gateway for that domains network 

4) sudo pg_dump --dbname=postgresql://<your_db_user>:<your_db_passwd>@<ip_of_rds>:5432/<db_name>> --schema-only -f sliderule-prov-sys-backup-FROM-slideruleearth-SCHEMA-ONLY-2023-02-06-13-23.sql
<br>
Where:<br>
-h to specify AWS RDS public dns Endpoint.<br>
-U to specify which user will connect to the PostgreSQL database server.<br>
db_user means database username<br>
-f is used to specify the output format of file.
db_name means database name<br>
name_of_dump_file means backup database file name<br>
.sql means backup database file as plain-text file containing SQL script.<br>
e.g. sudo pg_dump -h [hostname here] -U ps_admin -f ./testsliderule_a-unique-suffix.sql provsys

Once the file is created reverse the above changes by deselecting the public access.Then delete the new route and remove the rules you added to the security groups
i.e. all the changes made with your IP address<br>
<br>
For Restore:<br>

<br>
use pgadmin to create a new db with the name ps_postgres_db_a-unique-suffix 
<br>
Then restore db from aws rds backup file into new db as follows:
<br>
sudo cat ./testsliderule_a-unique-suffix.sql | docker exec -i ps-db psql -U ps_admin -d ps_postgres_db_a-unique-suffix<br>

<br>
This creates a new db to use. Stop the server and make the change in the environment variable used for the db name (in file .env.dev)
<br>
The make sure your django migration files are correct and match the db you are restoring with. Then restart to use the new DB by running the ps-web using 'make run' in the sliderule-pw-web directory

Then Drop the old dev db:<br>
Use PgAdmin4 to drop the database ps_postgres_db_<old_suffix>

# Synchronize testsliderule.org rds to slideruleearth.io

When delivering database changes it is important to make sure the migration files that are created in the test environment and that are merged into the main branch originate from the same set that exists in production. This prodedure outlines a process to deploy the testsliderule.org with snapshot of the slideruleearth.io (i.e. production) using the same version of software and (by definition migration files) that is running on production. This ensures a mirror copy of the database and software is running on testsliderule.org. Then we log into the testsliderule.org ps-web container and export the database. We can then import this database on our local development and run the local system with the new version of django software we want to deliver to generate the new migration files that are needed. These are generated from the production db/migration file set. The production set should be the set that is in the repo for that version of the software.

1) destroy testsliderule.org using:
   <pre>make destroy-testsliderule-org</pre>

2) deploy the testsliderule.org with the same VERSION of sw as production and with the most recent snapshot of the production db using:
    <pre>make deploy-to-testsliderule-org VERSION=[version running in prod]</pre>
    **IMPORTANT when prompted for enter the most recent snapshot of prod

3) Clean up the DB using the Django Admin panel (i.e. ps.slideruleearth.io/admin)
  * remove the organizations
  * remove all users except developers accounts and test accounts

4) create db-schema file on the container using following make target: (Will prompt for db password. Use the aws console and get rds_password from $(DOMAIN)/secrets):<pre>make ecs-ps-web-pg-dump-db-schema-in-testsliderule</pre>

5) download the pg dump file using:<pre>make ecs-ps-web-get-db-schema-from-testsliderule</pre>

6) remove the extra lines created by the session manager in the file that was created. They look like this:<pre>The Session Manager plugin was installed successfully. Use the AWS CLI to start a session.


Starting session with SessionId: ecs-execute-command-03ba0baba4d91a994
</pre>

7) copy the file to the DB_BACKUP_DIR

8) create a blank local test db with:<pre>make db-create-blank</pre>
9) restore the local db with (adjust for current filename):<pre>make db-restore-SCHEMA-FROM-sql-file DB_FILE=db.testsliderule-schema-[date].sql</pre>
10) Run the local system from test/prov-sys/ and add a superuser like this:<pre>$ make run
$ docker exec -it ps-web python manage.py createsuperuser --username admin --email support@mail.slideruleearth.io</pre>