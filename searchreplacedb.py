import pprint
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.engine import reflection
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm.session import sessionmaker
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer

from phpserialize import serialize, unserialize
__author__ = 'Jonathan Liuti'

def recursive_unserialize_replace(search, replace, data, serialized = False):
    try:
        recursive_unserialize_replace(search, replace, unserialize(data), True)

    except Exception, e:

        #HANDLE THE ERROR REPORT HERE
        if e.message.find('unexpected opcode') >= 0:
            pass
#            print 'this is not serialized data'
#            print data
        elif e.message.find('failed expectation') >= 0:
            print 'You have a badly encoded serialized data in'
            pprint.pprint(data)

        # THIS IS EITHER A CORRUPT SERIALIZED DATA OR NOT A SERIALIZED DATA
        # DO THE STANDARD WORK.
        tmpDict = {}
        if (type(data) in (dict, list, tuple)):
            for key, value in dict.iteritems(data):
                tmpDict[key.replace(search, replace)] = recursive_unserialize_replace(search, replace, value, False)
            data = tmpDict
        elif(type(data) == str):
            data = data.replace(search, replace)

        if serialized == True:
            return serialize(data)
        else:
            return data



def db_searchreplace(db_name, db_user, db_password, db_host, search, replace ):
    engine = create_engine("mysql://%s:%s@%s/%s" % (db_user, db_password, db_host, db_name ))
    #inspector = reflection.Inspector.from_engine(engine)
    #print inspector.get_table_names()
    meta = MetaData()
    meta.bind = engine
    meta.reflect()

    Session = sessionmaker(engine)


    Base = declarative_base(metadata=meta)
    session = Session()

    tableClassDict = {}
    for table_name, table_obj in dict.iteritems(Base.metadata.tables):
        try:
            tableClassDict[table_name] = type(str(table_name), (Base,), {'__tablename__': table_name, '__table_args__':{'autoload' : True, 'extend_existing': True} })
    #        class tempClass(Base):
    #            __tablename__ = table_name
    #            __table_args__ = {'autoload' : True, 'extend_existing': True}
    #            foo_id = Column(Integer, primary_key='temp')
            for row in session.query(tableClassDict[table_name]).all():
                for column in table_obj._columns.keys():
                    data_to_fix = getattr(row, column)
                    fixed_data = recursive_unserialize_replace( search, replace, data_to_fix, False)

                    setattr(row, column, fixed_data)
                    #print fixed_data
        except Exception, e:
            print e


#db_searchreplace('sandbox_tv', 'root', 'icsfyesfa:xps', 'localhost', 'http://sandbox_tv.voxteneo.dev', 'http://coucoucoco.voxteneo.dev')
db_searchreplace('sandbox_tv', 'root', 'icsfyesfa:xps', 'localhost', 'contact-form-7', 'okc')