#! /usr/bin/env python
#-*- coding: utf-8 -*-
# Jonathan Liuti for Vox Teneo
# Copyright (C) 2011 Jonathan Liuti
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# REQUIREMENTS:
# This script is intended to be run on debian based system.
# It requires elevated rights to run properly so please use 'sudo'
# Required application: svn client, mysql client, 


import argparse, ConfigParser, json, os, pdb, urllib, tarfile, shutil,pwd, getpass,subprocess,MySQLdb,datetime, random, string, glob, sys

#Init Configuration
config = ConfigParser.ConfigParser()
config.read('config.ini')
current_env = config.get('general', 'env')

#Utility Functions
def get_database_list(mysql_host, mysql_user, mysql_password):
   database_list_cmd="mysql -u %s -p%s -h %s --silent -N -e 'show databases'" % (mysql_user, mysql_password, mysql_host)
   database_list = []
   for database in os.popen(database_list_cmd).readlines():
      database_list.append(database.strip())
   return database_list

def check_root():
   if not os.geteuid()==0:
      sys.exit("\nYou need to be root to run this command.\n")

#Main Functions
def init_site(args):
   check_root()
   if not os.path.isfile('default.vhost'):
      raise Exception('default.vhost file required and not found.')
   #Define initial vars 
   wwwdir = config.get('apache', 'wwwdir')
   for site in args.sites:
      site = 'site_'+site
      sitedomain = config.get(site,current_env+'_domain_name')
      #Take svn url from argument or config file
      svn_url = None
      if args.svn_url:
         svn_url = args.svn_url
      elif config.has_option(site,'svn_url'):
         svn_url = config.get(site,'svn_url')

      #create the sitedir in wwwdir
      sitedir = (os.path.expanduser(wwwdir)+os.sep+sitedomain).replace('//','/')
      if not os.path.exists(sitedir):
         os.makedirs(sitedir)
      
      #create the apache2 vhost 
      sed_expression = "sed -e 's/'default.domain.ext'/'%s'/' default.vhost > %s" % (sitedomain, os.path.expanduser(config.get('apache', 'vhostdir'))+os.sep+sitedomain.replace('//','/'))
      os.system(sed_expression)

      #enable the vhost
      #TODO optionnalize this part aka apache vhost enable and reload
      os.system("a2ensite "+sitedomain)
      os.system("/etc/init.d/apache2 reload")

      #add the domain to the host file
      #TODO do it the clean python way
      with open('/etc/hosts') as host:
         os.system('echo "127.0.0.1\t\t%s" >> /etc/hosts' % sitedomain)
      #get the latest wordpress release and checkout the files from svn
      os.chdir(sitedir)
      if svn_url:   
         if config.has_option(site,'svn_user'):
            svn_user = config.get(site,'svn_user')
         else:
            svn_user = config.get('svn', 'user')
         if config.has_option(site,'svn_password'):
            svn_password = config.get(site,'svn_password')
         else:
            svn_password = config.get('svn','password')
         os.system("svn checkout %s . --username %s --password %s" % (svn_url, svn_user , svn_password))

      #TODO Implement a local system for keeping already downloaded wordpress release
      if config.has_option(site,'wp_version'):
         wp_version = "wordpress-"+config.get(site,'wp_version')
      else:
         wp_version = config.get('wordpress','wp_default_version')

      urllib.urlretrieve('http://wordpress.org/'+wp_version+'.tar.gz','tmp.tar.gz')
      tar = tarfile.open("tmp.tar.gz", "r:gz")
      tar.extractall()
      os.remove("tmp.tar.gz")

      #Check if the svn repo contained wp-content folder or not.
      if os.path.isdir('wp-content'):
         shutil.rmtree("wordpress/wp-content/")
      #TODO make this work ? shutil.move("wordpress/*",".")
      os.system("mv wordpress/* .")
      shutil.rmtree("wordpress")
      os.system('chown -R %s:%s .' % (config.get('apache','user'),config.get('apache','group')))

def init_database(args):
   
   mysql_user = config.get('mysql_'+args.mysql_host,'user')
   mysql_password = config.get('mysql_'+args.mysql_host,'password') 
   mysql_host = config.get('mysql_'+args.mysql_host, 'host') 
   
   database_list = get_database_list(mysql_host,mysql_user,mysql_password)

   if database_list:
      for site in args.sites:
         site_section = 'site_'+site
         db_name = config.get(site_section,'db_name')
         db_user = config.get(site_section, 'db_user')
         #If password is already set up in the config keep it - otherwise generate it
         db_password = config.has_option(site_section,'db_password') and config.get(site_section, 'db_password') or (''.join(random.choice(string.ascii_letters + string.digits) for x in range(16)))
         if not db_name:
            print "No database name provided"
            continue
         elif db_name in database_list:
            print "Database %s already exists" % db_name
            continue
         else:
            #TODO use the correct domain localhost is not always the right value
            create_user_query = "CREATE USER '%s'@'localhost' IDENTIFIED BY '%s'; CREATE DATABASE %s; GRANT ALL ON *.* TO '%s'@'localhost';" % (db_user, db_password, db_name, db_user)
            cmd="mysql -u %s -p%s -h %s --silent -N -e \"%s\"" % (mysql_user, mysql_password, mysql_host, create_user_query)
            if os.system(cmd) != 0:
               print "The init database failed."
            else:
               print "Database init succesfull.\ndb_name:%s \nuser:%s \npassword:(see config.ini)" % (db_name,db_user)

               if not config.has_option(site_section,'db_password') or not config.get(site_section,'db_password'): 
                  config.set(site_section,'db_password',db_password)
                  with open('config.ini', 'w') as configfile:
                     config.write(configfile)

   else:
      print "The init database failed."

def backup_database(args):  
   
   mysql_section = 'mysql_'+args.source_server
   mysql_user = config.get(mysql_section,'user')
   mysql_password = config.get(mysql_section,'password') 
   mysql_host = config.get(mysql_section, 'host') 
   mysql_env = config.get(mysql_section,'env')
   backupdir = os.path.expanduser(config.get('general','backupdir'))

   if not os.path.exists(backupdir):
      os.makedirs(backupdir)

   database_list = get_database_list(mysql_host, mysql_user,mysql_password)
   if database_list:
      for site in args.sites:
         site_section = 'site_'+site
         db_name = config.get(site_section,'db_name')
         sitedomain = config.get(site_section,mysql_env+'_domain_name')
         filestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
         filename = backupdir+os.sep+db_name+"-"+args.source_server+"-"+filestamp+".sql"
         if db_name in database_list:
            result = os.system("mysqldump -u %s -p%s -h %s -e --opt -c %s | sed -e 's/'%s'/'domain_to_replace'/g' |gzip -c > %s.gz" % (mysql_user, mysql_password, mysql_host, db_name, sitedomain, filename))
#TODO add an option to automatically put the db under svn - commit and stuff.
#            result_sed = os.system("sed -e 's/'"+sitedomain+"'/'domain_to_replace'/' "+filename+" > "+filename)
            if result != 0:
               print "Backup failed."
            else:               
               print "Backup succesfull."
         else:
            print "Database %s does not exist on %s" % (database, mysql_host)
   else:
      print "No database found in source %s" % (mysql_host)

def restore_database(args):
   site_section = 'site_'+args.site
   backupdir = os.path.expanduser(config.get('general','backupdir'))
   db_name = config.get(site_section, 'db_name')
   backup_list = glob.glob(backupdir+os.sep+db_name+'*.sql.gz'.replace('//','/'))
   backup_list.sort()
   mysql_section = 'mysql_'+args.destination_server
   mysql_user = config.get(mysql_section,'user')
   mysql_password = config.get(mysql_section,'password') 
   mysql_host = config.get(mysql_section, 'host') 
   mysql_env = config.get(mysql_section,'env')
   sitedomain = config.get(site_section,mysql_env+'_domain_name')
 
   counter = 0
   for backup in backup_list:
      print "(%d) %s" % (counter,backup.rpartition('/')[2].partition('.')[0]) 
      counter+=1
   #Control user input
   while True:
      try:
         db_number = int(raw_input("Database number to restore: "))
         if 0 <= db_number < len(backup_list):
            break
         else: 
            print "Error:this number doesn't reference any database"
      except ValueError:
         print "Error: please enter a number"
         continue
   confirm = raw_input("Are you sure that you want to restore %s on server %s (yes/no) " % (backup_list[db_number], mysql_host))
   if confirm == 'yes' or confirm == 'y':
      result = os.system("gunzip < %s | sed -e 's/'domain_to_replace'/'%s'/g' | mysql -h %s -u %s -p%s %s" % (backup_list[db_number], sitedomain, mysql_host, mysql_user, mysql_password, db_name))
      if result != 0 :
         print "Restore failed"
      else:
         print "Restore succesfull"
   else:
      print "Restore failed"
   
def delete_sites(args):
   print "Delete command occurs here"

def synch_upload_datas(args):
   print "synch_upload_datas command occurs here"

def update_site(args):
   check_root()
   wwwdir = config.get('apache', 'wwwdir')
   for site in args.sites:
      site = 'site_'+site
      sitedomain = config.get(site,current_env+'_domain_name')
      sitedir = (os.path.expanduser(wwwdir)+os.sep+sitedomain).replace('//','/')     
      os.chdir(sitedir)
    
      #TODO Implement a local system for keeping already downloaded wordpress release
      if args.wp_version == 'latest':
         wp_version = 'latest'
      else: 
         wp_version = "wordpress-"+args.wp_version
      os.system('rm -rf wp-admin wp-includes')
      urllib.urlretrieve('http://wordpress.org/'+wp_version+'.tar.gz','tmp.tar.gz')
      tar = tarfile.open("tmp.tar.gz", "r:gz")
      tar.extractall()
      os.remove("tmp.tar.gz")

      #TODO make this work ? shutil.move("wordpress/*",".")
      os.system("mv wordpress/* .")
      shutil.rmtree("wordpress")
      os.system('chown -R %s:%s .' % (config.get('apache','user'),config.get('apache','group')))


# ARGUMENT PARSER SECTION #
###########################

# retrieve the site choices values
def get_site(section):
   if section.startswith('site_'):
      return section[5:]
# iterate through the sections name and only get those that starts with site_ then remove None results
site_choices = filter(None,[get_site(site) for site in config.sections() ])

def get_mysql_server(section):
   if section.startswith('mysql_'):
      return section[6:]
mysql_server_choices = filter(None,[get_mysql_server(mysql_server) for mysql_server in config.sections()])

# define the argument parser here #
###################################
parser = argparse.ArgumentParser(description='Wordpress management tools.')
subparsers = parser.add_subparsers(title='Commands available', help='type the action followed by -h to get additional help')

# define parser for the init-site command
parser_init_site = subparsers.add_parser('init-site',help='Creates a local wordpress site, configures apache vhost and optionally retrieves custom wp-content folder with svn.')

parser_init_site.add_argument('sites', metavar='sites', choices=site_choices, type=str, nargs='+', help='The site\'s name as defined in the config file section eg: my-site')

parser_init_site.add_argument('-d','--dir', dest='wwwdir', help='The directory where the site will be created.')

parser_init_site.add_argument('-s','--svn', dest='svn_url', default=None, help='The svn url used to get datas from. Default: %(default)s aka will be ignored')

parser_init_site.set_defaults(func=init_site)

# define parser for the update-site command
parser_update_site = subparsers.add_parser('update-site',help='Update selected site to another wordpress version (default:latest version)')

parser_update_site.add_argument('sites', metavar='sites', choices=site_choices, type=str, nargs='+', help='The site\'s name as defined in the config file section eg: my-site')

parser_update_site.add_argument('-v','--version', dest='wp_version', default='latest', help='The version of wordpress to update to. Default: %(default)s version')

parser_update_site.set_defaults(func=update_site)


#define parser for the init-db command

parser_init_database = subparsers.add_parser('init-db',help='Initialize a database to your local mysql and optionally create user/permission accordingly.')

parser_init_database.add_argument('sites', metavar='sites',choices=site_choices, type=str, nargs='+', help='The site you want to init the database for.')

parser_init_database.add_argument('-cu','--create-user', dest='create_user', default=False, action="store_true", help='Append this parameter if you want to create user and database along with creation of the db')

parser_init_database.add_argument('--host', dest='mysql_host', required=True, choices=mysql_server_choices, help='Mysql server where the database will be created')

parser_init_database.set_defaults(func=init_database)

#define parser for the backup-db command
parser_backup_database = subparsers.add_parser('backup-db',help='backup a database from source to backup folder')

parser_backup_database.add_argument('sites', metavar='sites', type=str, nargs='+', choices=site_choices, help='The name of the site from which you want to backup the db (separated by spaces)')

parser_backup_database.add_argument('-s','--source-server', dest='source_server', required=True, help='Database(s) will be backuped FROM this location')

parser_backup_database.set_defaults(func=backup_database)

#define parser for the restore-db command
parser_restore_database = subparsers.add_parser('restore-db',help='Restore a database from file to destination server')

parser_restore_database.add_argument('site', metavar='site', type=str, help='The name of the site you want to restore the db to.')

parser_restore_database.add_argument('-d','--destination-server', dest='destination_server', required=True, help='Database(s) will be restored to this location')

parser_restore_database.set_defaults(func=restore_database)
#parse arguments and call the related function
args = parser.parse_args() 
args.func(args)
