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


import argparse, ConfigParser, json, os, urllib, tarfile, shutil, pwd, getpass, subprocess, datetime, random, string, glob, sys

from wordpress_xmlrpc import Client
from lib.python_wordpress_xmlrpc.plugins import GetPluginsList
#Init configuration Parser
class Sword(object):
    """Utility class to mass manage your wordpress installs"""

    def __init__(self):
        self.config = ConfigParser.ConfigParser()
        if not self.config.read('config.ini'):
            raise Exception(
                "Error accessing your config file. config.ini should be located in the same folder as Sword")
        self.current_env = self.config.get('general', 'env')
        self.wwwdir = self.config.get('apache', 'wwwdir')

    #Utility Functions
    def get_database_list(self, mysql_host, mysql_user, mysql_password):
        database_list_cmd = "mysql -u %s -p%s -h %s --silent -N -e 'show databases'" % (
        mysql_user, mysql_password, mysql_host)
        database_list = []
        for database in os.popen(database_list_cmd).readlines():
            database_list.append(database.strip())
        return database_list

    def check_root(self):
        if not os.geteuid() == 0:
            sys.exit("\nYou need to be root to run this command.\n")

    def get_site(self, section):
        '''Retrieve the site name from section name'''
        if section.startswith('site_'):
            return section[5:]


    # iterate through the sections name and only get those that starts with site_ then remove None results
    @property
    def site_choices(self):
        return sorted(filter(None, [self.get_site(site) for site in self.config.sections()]))

    def select_list(self, list_items, header_message, select_message):
        """Helper to display a selectable list"""
        print(header_message)
        for number, value in enumerate(list_items):
            print( "(%d) %s" % (number, value) )
        while True:
            try:
                choice = int(raw_input("%s: " % select_message))
                if  len(list_items) < choice < 0:
                    raise Exception
                return list_items[choice]
            except:
                print('Please insert a valid number in the [0,%d] interval' % len(list_items) - 1)

    def confirm_input(self, confirm_message):
        """Helper to display a confirmation message"""
        confirm = raw_input("%s (yes/no): " % (confirm_message))
        if confirm == 'yes' or confirm == 'y':
            return True
        else:
            sys.exit("Action canceled.")

    def required_input(self, message):
        """Helper to display a confirmation message"""
        result = ''
        while(result == ''):
            result = raw_input("%s: " % (message))
        return result

    def get_mysql_server(self, section):
        if section.startswith('mysql_'):
            return section[6:]

    @property
    def mysql_server_choices(self):
        return filter(None, [self.get_mysql_server(mysql_server) for mysql_server in self.config.sections()])

    #Main Script Functions
    def init_site(self, args):
#        self.check_root()
        if not os.path.isfile('default.vhost'):
            raise Exception('default.vhost file required and not found.')

        if args.interractive:

            sites = [self.required_input("Please type in an identifier for this site (eg: voxteneo)")]
            site_section = 'site_'+sites[0]
            self.config.add_section(site_section)

            sitedomain = self.required_input("What is the domain for this site (eg: www.voxteneo.com)")
            self.config.set(site_section, self.current_env + '_domain_name', sitedomain)

            admin_email = self.required_input("What is admin's email")
            self.config.set(site_section, 'admin_email', admin_email)

            #apache_user = raw_input("What is apache user to be set in the vhost (leave blank for config default): ")
            apache_user = None
            if not apache_user:
                if self.config.has_option('apache', 'user'):
                    apache_user = self.config.get('apache', 'user')
                else:
                    raise Exception("You need to define the user in the apache section of your config file.")

            #apache_group = raw_input("What is apache group to be set in the vhost (leave blank for config default): ")
            apache_group = None
            if not apache_group:
                if self.config.has_option('apache', 'group'):
                    apache_group = self.config.get('apache', 'group')
                else:
                    raise Exception("You need to define the group in the apache section of your config file")

            versioning = self.select_list(['Git','Svn', 'None'], '', 'Which versioning system will you be using?')

            if versioning == 'Git':
                git_url = self.required_input("What is the git url (eg: git@gitlab.voxteneo.com:test.git)")
                self.config.set(site_section, 'git_url', git_url)
                git_folder = self.required_input("Git clone destination folder name (eg: test)")
                self.config.set(site_section, 'git_folder', git_folder)

            elif versioning == 'Svn':
                svn_url = self.required_input("What is the svn url (eg: https://svn.voxteneo.com/test/)")
                self.config.set(site_section, 'svn_url', svn_url)
                svn_user = self.required_input("What is the svn user")
                self.config.set(site_section, 'svn_user', svn_user)
                svn_password = self.required_input("What is the svn password")
                self.config.set(site_section, 'svn_password', svn_password)
            else:
                versioning = None

            wp_version = raw_input("Which version of Wordpress do you want to install (leave empty for the latest): ")
            if not wp_version:
                wp_version = self.config.get('wordpress', 'wp_default_version')
            else:
                self.config.set(site_section, 'wp_version', wp_version)

            #Save the new values in the config
            with open('config.ini', 'w') as configfile:
                self.config.write(configfile)
        else:
            sites = args.sites

        #Define initial vars
        for site in sites:
            site = 'site_' + site
            if not args.interractive:
                sitedomain = self.config.get(site, self.current_env + '_domain_name')
                #Take admin email from site section or general SECTION
                if self.config.has_option(site, 'admin_email'):
                    admin_email = self.config.get(site, 'admin_email')
                elif self.config.has_option('general', 'admin_email'):
                    admin_email = self.config.get('general', 'admin_email')
                else:
                    raise Exception(
                        "You need to define admin_email in either general option section or %s section of your config file" % (
                        site))

                #Take apache user and group from apache section
                if self.config.has_option('apache', 'user'):
                    apache_user = self.config.get('apache', 'user')
                else:
                    raise Exception("You need to define the user in the apache section of your config file")

                if self.config.has_option('apache', 'group'):
                    apache_group = self.config.get('apache', 'group')
                else:
                    raise Exception("You need to define the group in the apache section of your config file")

                #Take svn url from argument or config file
                versioning = None
                svn_url = None
                if args.svn_url:
                    versioning = 'Svn'
                    svn_url = args.svn_url
                elif self.config.has_option(site, 'svn_url'):
                    versioning = 'Svn'
                    svn_url = self.config.get(site, 'svn_url')

                if self.config.has_option(site, 'svn_user'):
                    svn_user = self.config.get(site, 'svn_user')
                else:
                    svn_user = self.config.get('svn', 'user')
                if self.config.has_option(site, 'svn_password'):
                    svn_password = self.config.get(site, 'svn_password')
                else:
                    svn_password = self.config.get('svn', 'password')

                #OR Take git url from argument or config file
                git_url = None
                if args.git_url:
                    versioning = 'Git'
                    git_url = args.git_url
                elif self.config.has_option(site, 'git_url'):
                    versioning = 'Git'
                    git_url = self.config.get(site, 'git_url')

                git_folder = None
                if args.git_folder:
                    git_folder = args.git_folder
                elif self.config.has_option(site, 'git_folder'):
                    git_folder = self.config.get(site, 'git_folder')

                if self.config.has_option(site, 'wp_version'):
                    wp_version = "wordpress-" + self.config.get(site, 'wp_version')
                else:
                    wp_version = self.config.get('wordpress', 'wp_default_version')



            #create the sitedir in wwwdir
            sitedir = (os.path.expanduser(self.wwwdir) + os.sep + sitedomain).replace('//', '/')
            if not os.path.exists(sitedir):
                os.makedirs(sitedir)

            #create the apache2 vhost

            available_site_file = (
            os.path.expanduser(self.config.get('apache', 'vhostdir')) + os.sep + sitedomain).replace('//', '/')
            sed_expression = "sed -e 's/'{default.domain.ext}'/'%s'/' default.vhost > %s" % (
            sitedomain, available_site_file)
            os.system(sed_expression)

            sed_expression = "sed -i -e 's#'{sitedir}'#'%s'#' %s" % (sitedir, available_site_file)
            os.system(sed_expression)

            sed_expression = "sed -i -e 's#'{admin_email}'#'%s'#' %s" % (admin_email, available_site_file)
            os.system(sed_expression)

            sed_expression = "sed -i -e 's#'{apache_user}'#'%s'#' %s" % (apache_group, available_site_file)
            os.system(sed_expression)

            sed_expression = "sed -i -e 's#'{apache_group}'#'%s'#' %s" % (apache_group, available_site_file)
            os.system(sed_expression)

            #enable the vhost
            #TODO optionnalize this part aka apache vhost enable and reload
            os.system("a2ensite " + sitedomain)
            os.system("/etc/init.d/apache2 reload")

            #add the domain to the host file
            #TODO do it the clean python way
            with open('/etc/hosts') as host:
                os.system('echo "127.0.0.1\t\t%s" >> /etc/hosts' % sitedomain)

            #get the latest wordpress release and checkout the files from svn

            if versioning == 'Svn':
                os.chdir(sitedir)
                os.system("svn checkout %s . --username %s --password %s" % (svn_url, svn_user, svn_password))

            # Or GIT
            elif versioning == 'Git':
                os.chdir('/tmp')
                default_user = self.config.get('general', 'default_user')
                git_tmp = '/tmp/%s' % git_folder
                os.system("sudo -u %s git clone %s" % (default_user, git_url))
                shutil.rmtree(sitedir)
                shutil.copytree(git_tmp, sitedir)
                shutil.rmtree(git_tmp)
                os.chdir(sitedir)

            else:
                os.chdir(sitedir)

            #TODO Implement a local system for keeping already downloaded wordpress release
            urllib.urlretrieve('http://wordpress.org/' + wp_version + '.tar.gz', 'tmp.tar.gz')
            tar = tarfile.open("tmp.tar.gz", "r:gz")
            tar.extractall()
            os.remove("tmp.tar.gz")

            #Check if the svn or git repo contained wp-content folder or not.
            if os.path.isdir('wp-content'):
                shutil.rmtree("wordpress/wp-content/")
                #TODO make this work ? shutil.move("wordpress/*",".")
            os.system("mv wordpress/* .")
            shutil.rmtree("wordpress")
            os.system('chown -R %s:%s .' % (apache_group, apache_user))

    def init_database(self, args):

        if args.mysql_server:
            mysql_server =  args.mysql_server
        else:
            mysql_server = self.select_list(self.mysql_server_choices, "What is your mysql server? ", "Choose a server where to create the database.")

        mysql_user = self.config.get('mysql_' + mysql_server, 'user')
        mysql_password = self.config.get('mysql_' + mysql_server, 'password')
        mysql_host = self.config.get('mysql_' + mysql_server, 'host')            

        if args.interractive :
            sites = [self.select_list(self.site_choices, "Sites", "Choose the site related to this database.")]
            site_section = 'site_'+sites[0]

#            mysql_user = raw_input("What is your mysql username (Leave blank for the config default)? ")
#            if not mysql_user:
#                mysql_user = self.config.get('mysql_' + mysql_server, 'user')
#                self.config.set(site_section, 'user', mysql_user)
#
#            mysql_password = raw_input("What is your mysql password (Leave blank for the config default)? ")
#            if not mysql_password:
#                mysql_password = self.config.get('mysql_' + mysql_server, 'password')
#                self.config.set(site_section, 'password', mysql_password)
#
#            mysql_host = raw_input("What is your mysql host (Leave blank for the config default)? ")
#            if not mysql_host:
#                mysql_host = self.config.get('mysql_' + mysql_server, 'host')
#                self.config.set(site_section, 'password', mysql_password)

            db_name = raw_input("What is your db name (Leave blank for the config default)? ")
            if not db_name:
                db_name = self.config.get(site_section, 'db_name')
                self.config.set(site_section, 'db_name', db_name)

            db_user = raw_input("What is your db user (Leave blank for the config default)? ")
            if not db_user:
                db_user = self.config.get(site_section, 'db_user')
                self.config.set(site_section, 'db_user', db_user)

            db_password_is_valid = False
            while (not db_password_is_valid):
                db_password = raw_input("What is your db password (Leave blank for the config default or automatic generation)? ")
                if not db_password:
                    db_password = self.config.has_option(site_section, 'db_password') and self.config.get(site_section,
                        'db_password') or (''.join(random.choice(string.ascii_letters + string.digits) for x in range(16)))
                    db_password_is_valid = True
                else:
                    db_password2 =  self.required_input("Please confirm your db password")
                    if db_password == db_password2:
                        db_password_is_valid = True
        else:
            sites = args.sites


        database_list = self.get_database_list(mysql_host, mysql_user, mysql_password)

        if database_list:
            for site in sites:
                if not args.interractive:
                    site_section = 'site_' + site
                    db_name = self.config.get(site_section, 'db_name')
                    db_user = self.config.get(site_section, 'db_user')

                    #If password is already set up in the config keep it - otherwise generate it
                    db_password = self.config.has_option(site_section, 'db_password') and self.config.get(site_section,
                        'db_password') or (''.join(random.choice(string.ascii_letters + string.digits) for x in range(16)))

                if not db_name:
                    print "No database name provided"
                    continue
                elif db_name in database_list:
                    print "Database %s already exists" % db_name
                    continue
                else:
                    #TODO use the correct domain localhost is not always the right value
                    create_user_query = "CREATE USER '%s'@'localhost' IDENTIFIED BY '%s'; CREATE DATABASE %s; GRANT ALL ON *.* TO '%s'@'localhost';" % (
                    db_user, db_password, db_name, db_user)
                    cmd = "mysql -u %s -p%s -h %s --silent -N -e \"%s\"" % (
                    mysql_user, mysql_password, mysql_host, create_user_query)
                    if os.system(cmd) != 0:
                        print "The init database failed."
                    else:
                        print "Database init succesfull.\ndb_name:%s \nuser:%s \npassword:(see config.ini)" % (
                        db_name, db_user)

                        if not self.config.has_option(site_section, 'db_password') or not self.config.get(site_section,
                            'db_password'):
                            self.config.set(site_section, 'db_password', db_password)
                            with open('config.ini', 'w') as configfile:
                                self.config.write(configfile)
        else:
            print "The init database failed."

    def backup_database(self, args):
        mysql_section = 'mysql_' + args.source_server
        mysql_user = self.config.get(mysql_section, 'user')
        mysql_password = self.config.get(mysql_section, 'password')
        mysql_host = self.config.get(mysql_section, 'host')
        mysql_env = self.config.get(mysql_section, 'env')

        backupdir = os.path.expanduser(self.config.get('general', 'backupdir'))
        if not os.path.exists(backupdir):
            os.makedirs(backupdir)

        database_list = self.get_database_list(mysql_host, mysql_user, mysql_password)
        if database_list:
            for site in args.sites:
                site_section = 'site_' + site
                db_name = self.config.get(site_section, 'db_name')
                sitedomain = self.config.get(site_section, mysql_env + '_domain_name')
                filestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                filename = backupdir + os.sep + db_name + "-" + args.source_server + "-" + filestamp + ".sql"
                if db_name in database_list:
                    result = os.system(
                        "mysqldump -u %s -p%s -h %s -e --opt -c %s | sed -e 's/'%s'/'domain_to_replace'/g' |gzip -c > %s.gz" % (
                        mysql_user, mysql_password, mysql_host, db_name, sitedomain, filename))

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

    def restore_database(self, args):
        site_section = 'site_' + args.site
        backupdir = os.path.expanduser(self.config.get('general', 'backupdir'))
        db_name = self.config.get(site_section, 'db_name')
        backup_list = glob.glob(backupdir + os.sep + db_name + '*.sql.gz'.replace('//', '/'))
        backup_list.sort()
        mysql_section = 'mysql_' + args.destination_server
        mysql_user = self.config.get(mysql_section, 'user')
        mysql_password = self.config.get(mysql_section, 'password')
        mysql_host = self.config.get(mysql_section, 'host')
        mysql_env = self.config.get(mysql_section, 'env')

        if mysql_env == 'prod':
            confirm = self.confirm_input(
                "Warning: You are going to restore something on the production.\nYou may loose data by doing this.\nDo you want to continue?")
            if not confirm:
                print "Cancelled by user"
        sitedomain = self.config.get(site_section, mysql_env + '_domain_name')

        counter = 0
        for backup in backup_list:
            print "(%d) %s" % (counter, backup.rpartition('/')[2].partition('.')[0])
            counter += 1
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

        confirm = self.confirm_input(
            "Are you sure that you want to restore %s on server %s" % (backup_list[db_number], mysql_host))

        if confirm:
            result = os.system("gunzip < %s | sed -e 's/'domain_to_replace'/'%s'/g' | mysql -h %s -u %s -p%s %s" % (
            backup_list[db_number], sitedomain, mysql_host, mysql_user, mysql_password, db_name))
            if result != 0:
                print "Restore failed"
            else:
                print "Restore succesfull"

    def delete_sites(self, args):
        #TODO IMPLEMENT !
        print "Delete command occurs here"

    def synch_upload_datas(self, args):
        #TODO IMPLEMENT !
        print "synch_upload_datas command occurs here"

    def install_debug_tools(self, args):
        #TODO IMPLEMENT !
        print "this will install plugins and tools for debuging"

    def remove_debug_tools(self, args):
        #TODO IMPLEMENT !
        print "removes dev tools"

    def update_site(self, args):
        self.check_root()
        for site in args.sites:
            site = 'site_' + site
            sitedomain = self.config.get(site, self.current_env + '_domain_name')
            sitedir = (os.path.expanduser(self.wwwdir) + os.sep + sitedomain).replace('//', '/')
            os.chdir(sitedir)

            #TODO Implement a local system for keeping already downloaded wordpress release
            if args.wp_version == 'latest':
                wp_version = 'latest'
            else:
                wp_version = "wordpress-" + args.wp_version
            os.system('rm -rf wp-admin wp-includes')
            urllib.urlretrieve('http://wordpress.org/' + wp_version + '.tar.gz', 'tmp.tar.gz')
            tar = tarfile.open("tmp.tar.gz", "r:gz")
            tar.extractall()
            os.remove("tmp.tar.gz")

            #TODO make this work ? shutil.move("wordpress/*",".")
            os.system("mv wordpress/* .")
            shutil.rmtree("wordpress")
            os.system('chown -R %s:%s .' % (self.config.get('apache', 'user'), self.config.get('apache', 'group')))

    def install_plugins(self, args):
        #TODO IMPLEMENT !
        print "This will let you install plugins based on a configurable selection - could even add group-package and preselect. Would be nice to offer to install from local or remote locations"

    def update_plugin(self, args):
        """Utility to batch update your plugins."""
        #self.check_root()
        site = self.select_list(self.site_choices, "Available websites", "Please select a website")
        site = 'site_' + site
        #TODO replace domain - user and  password with config data
        wp_xmlrpc_client = Client('http://companywriters.voxteneo.dev/xmlrpc.php', 'user', 'pass')
        wp_xmlrpc_client.call(GetPluginsList())

sword_instance = Sword()
# ARGUMENT PARSER SECTION #
###########################
# define the argument parser here #
###################################
parser = argparse.ArgumentParser(description='Wordpress management tools.')
subparsers = parser.add_subparsers(title='Commands available',
    help='type the action followed by -h to get additional help')

# define parser for the init-site command
parser_init_site = subparsers.add_parser('init-site',
    help='Creates a local wordpress site, configures apache vhost and optionally retrieves custom wp-content folder with svn.')

parser_init_site.add_argument('-s', '--sites', dest='sites', metavar='sites', choices=sword_instance.site_choices, type=str, nargs='*',
    help='The site\'s name as defined in the config file section eg: my-site')

parser_init_site.add_argument('-d', '--dir', dest='sword_instance.wwwdir',
    help='The directory where the site will be created.')

parser_init_site.add_argument('--svn', dest='svn_url', default=None,
    help='The svn url used to get datas from. Default: %(default)s aka will be ignored')

parser_init_site.add_argument('-gu', '--git_url', dest='git_url', default=None,
    help='The git url used to get datas from. Default: %(default)s aka will be ignored')

parser_init_site.add_argument('-gf', '--git_folder', dest='git_folder', default=None,
    help='The git folder used to put datas in. Default: %(default)s aka will be ignored')

parser_init_site.add_argument('-i', '--interactive', dest='interractive', type=bool, nargs='?', default=False, const=True,
    help='Activate interactive mode, site creation is done with a sequence of Question / Answer and datas are stored in the config file automatically. Default: %(default)s aka will be inactive')

parser_init_site.set_defaults(func=sword_instance.init_site)

# define parser for the update-site command
parser_update_site = subparsers.add_parser('update-site',
    help='Update selected site to another wordpress version (default:latest version)')

parser_update_site.add_argument('sites', metavar='sites', choices=sword_instance.site_choices, type=str, nargs='+',
    help='The site\'s name as defined in the config file section eg: my-site')

parser_update_site.add_argument('-v', '--version', dest='wp_version', default='latest',
    help='The version of wordpress to update to. Default: %(default)s version')

parser_update_site.set_defaults(func=sword_instance.update_site)


# define parser for the update-site command
parser_update_plugin = subparsers.add_parser('update-plugin', help='Batch update plugins on selected sites')

parser_update_plugin.set_defaults(func=sword_instance.update_plugin)

#define parser for the init-db command

parser_init_database = subparsers.add_parser('init-db',
    help='Initialize a database to your local mysql and optionally create user/permission accordingly.')

parser_init_database.add_argument('-s', '--sites', dest='sites', metavar='sites', choices=sword_instance.site_choices, type=str,
    help='The site you want to init the database for.')

parser_init_database.add_argument('-cu', '--create-user', dest='create_user', default=False, action="store_true",
    help='Append this parameter if you want to create user and database along with creation of the db')

parser_init_database.add_argument('--server', dest='mysql_server',
    choices=sword_instance.mysql_server_choices, help='Mysql server where the database will be created')

parser_init_database.add_argument('-i', '--interactive', dest='interractive', type=bool, nargs='?', default=False, const=True,
    help='Activate interactive mode, database creation is done with a sequence of Question / Answer and datas are stored in the config file automatically. Default: %(default)s aka will be inactive')

parser_init_database.set_defaults(func=sword_instance.init_database)

#define parser for the backup-db command
parser_backup_database = subparsers.add_parser('backup-db', help='backup a database from source to backup folder')

parser_backup_database.add_argument('sites', metavar='sites', type=str, nargs='+', choices=sword_instance.site_choices,
    help='The name of the site from which you want to backup the db (separated by spaces)')

parser_backup_database.add_argument('-s', '--source-server', dest='source_server', required=True,
    help='Database(s) will be backuped FROM this location')

parser_backup_database.set_defaults(func=sword_instance.backup_database)

#define parser for the restore-db command
parser_restore_database = subparsers.add_parser('restore-db', help='Restore a database from file to destination server')

parser_restore_database.add_argument('site', metavar='site', type=str,
    help='The name of the site you want to restore the db to.')

parser_restore_database.add_argument('-d', '--destination-server', dest='destination_server', required=True,
    help='Database(s) will be restored to this location')

parser_restore_database.set_defaults(func=sword_instance.restore_database)
#parse arguments and call the related Functions
args = parser.parse_args()
args.func(args)
