##Imports
import sys
import json
import argparse
from sfdaemon import SqlClient

# ----------------------------------------------------------------------------------------------------------------------
# This function builds and returns the argument parser used by this script.
# Args:
#   None
# Returns:
#   argparse.ArgumentParser: Configured parser for command line options.
# ----------------------------------------------------------------------------------------------------------------------
def BuildArgumentParser():
  Parser=argparse.ArgumentParser(prog="sql_test.py",description="Execute SQL query using SqlClient from sfd.py")
  Parser.add_argument("--con",dest="Con",required=True,help="Snowflake connection name")
  Parser.add_argument("--sql",dest="Sql",required=True,help="SQL query to execute")
  return Parser

# ----------------------------------------------------------------------------------------------------------------------
# This function parses the command line arguments and returns normalized options.
# Args:
#   None
# Returns:
#   tuple: (ConnectionName,SqlQuery)
# ----------------------------------------------------------------------------------------------------------------------
def ParseArguments():
  Parser=BuildArgumentParser()
  Args=Parser.parse_args(sys.argv[1:])
  return Args.Con,Args.Sql

# ----------------------------------------------------------------------------------------------------------------------
# This function runs the SQL query using SqlClient and prints execution outputs.
# Args:
#   None
# Returns:
#   int: Process exit code.
# ----------------------------------------------------------------------------------------------------------------------
def Main():

  #This code block parses command line arguments.
  ConnectionName,SqlQuery=ParseArguments()

  #This code block executes the SQL query against the selected connection.
  Client=SqlClient()
  Client.SetConnection(ConnectionName)
  Status,Message,Rows,Columns=Client.ExecuteSqlQuery(SqlQuery)

  #This code block handles execution failures and emits an error message.
  if Status==False:
    print(Message)
    return 1

  #This code block prints successful execution results as formatted JSON.
  Output={"status":True,"message":Message,"row_count":len(Rows),"columns":Columns,"rows":Rows}
  print(json.dumps(Output,indent=2,default=str))
  return 0

# ----------------------------------------------------------------------------------------------------------------------
# This code block is the script entry point that returns Main exit code to the OS.
# ----------------------------------------------------------------------------------------------------------------------
if __name__=="__main__":
  sys.exit(Main())
