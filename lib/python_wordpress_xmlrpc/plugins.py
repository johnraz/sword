from wordpress_xmlrpc import AuthenticatedMethod

class GetPluginsList(AuthenticatedMethod):
   '''Retrieve a list of plugins, their state and update status'''
   method_name = 'wri.getPluginsList'
   #method_args = ();
