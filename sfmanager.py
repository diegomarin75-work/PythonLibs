#Import libraries
import io
import tomllib
import pathlib
import threading
import contextlib

# ----------------------------------------------------------------------------------------------------------------------
# Encapsulates Snowflake connection helpers and background library preload.
# ----------------------------------------------------------------------------------------------------------------------
class SnowflakeManager:

  #Configuration constants
  _PRELOAD_LIBRARIES_TIMEOUT_SECS=30

  # ----------------------------------------------------------------------------------------------------------------------
  # Initialize the manager with the path to the Snowflake connections file.
  # Args:
  #   PreloadLibraries (bool): When True,Snowflake libraries are preloaded asynchronously in a background thread.
  #   ConnectionsFile (str): Location of the Snowflake connections definition file.
  #   ConnParameters (dict): Optional dictionary with connection parameters to use instead of a connections file.
  # ----------------------------------------------------------------------------------------------------------------------
  def __init__(self,PreloadLibraries=False,ConnectionsFile=None,ConnParameters=None,Debug=False):

    #Save parameters
    self._PreloadLibraries=PreloadLibraries
    self._ConnectionsFile=ConnectionsFile
    self._ConnParameters=ConnParameters
    self._Debug=Debug
    self._ExecutionDisabled=False
    self._DebugErrors=False

    #Initialize state
    self._ImportLibrariesError=None
    self._LibrariesReady=None
    self._SnowflakeConnect=None
    self._SnowflakeSplitStatements=None
    self._ConnectionObj=None
    self._ConnectionName=None

    #Preload snowflake libraries
    if PreloadLibraries==True:
      self._LibrariesReady=threading.Event()
      threading.Thread(target=self._ImportLibrariesDaemon,daemon=True).start()

  # ----------------------------------------------------------------------------------------------------------------------
  # Load Snowflake connector modules asynchronously and store references.
  # ----------------------------------------------------------------------------------------------------------------------
  def _ImportLibrariesDaemon(self):
    self._ImportLibrariesError=None
    try:
      from snowflake.connector import connect
      from snowflake.connector.util_text import split_statements
      self._SnowflakeConnect=connect
      self._SnowflakeSplitStatements=split_statements
    except Exception as Ex:
      self._ImportLibrariesError=f"Exception happened while loading snowflake libraries: {str(Ex)}"
    finally:
      if self._LibrariesReady is not None:
        self._LibrariesReady.set()

  # ----------------------------------------------------------------------------------------------------------------------
  # Ensure Snowflake libraries are loaded,blocking for the daemon to finish.
  # Returns:
  #   tuple[bool,str]: Success flag and a diagnostic message on failure.
  # ----------------------------------------------------------------------------------------------------------------------
  def _ImportLibraries(self):

    #Wait for daemon to finish if libraries are being preloaded
    if self._PreloadLibraries==True:
      self._LibrariesReady.wait(self._PRELOAD_LIBRARIES_TIMEOUT_SECS)
      if not self._LibrariesReady.is_set():
        Message=f"Snowflake libraries load timeout reached!"
        return False,Message

    #Import libraries again if preload failed or not enabled
    if self._SnowflakeConnect is None:
      self._ImportLibrariesDaemon()

    #Check library load exception
    if self._ImportLibrariesError is not None:
      return False,self._ImportLibrariesError

    #Return success
    return True,""

  # ----------------------------------------------------------------------------------------------------------------------
  # Gets the user name for the specified connection.
  # Args:
  #   ConnectionName (str): Logical connection name defined in the connections file.
  #                         When it is None,the connection parameters dictionary is used.
  # Returns:
  #   tuple[bool,str,str | None]: Success flag,message,and user name when successful.
  # ----------------------------------------------------------------------------------------------------------------------
  def GetConnectionUser(self,ConnectionName=None):

    #Get user name from connection parameters as provided from command line
    if self._ConnParameters is not None:
      if "user" in self._ConnParameters:
        UserName=self._ConnParameters["user"]
      else:
        Message=f"Unable to get user from connection parameters"
        return False,Message,None

    #Get user name from connections file for given connection name
    else:
      try:
        Config=tomllib.loads(pathlib.Path(self._ConnectionsFile).read_text())
      except Exception as Ex:
        Message=f"Cannot read connections file '{self._ConnectionsFile}': {str(Ex)}"
        return False,Message,None
      if ConnectionName in Config:
        if "user" in Config[ConnectionName]:
          UserName=Config[ConnectionName]["user"]
        else:
          Message=f"Unable to get user from connection '{ConnectionName}' in connections file"
          return False,Message,None
      else:
        Message=f"Connection '{ConnectionName}' not found in connections file"
        return False,Message,None

    #Return success
    return True,"",UserName

  # ----------------------------------------------------------------------------------------------------------------------
  # Open the configured Snowflake connection,reusing existing state when possible.
  # Args:
  #   ConnectionName (str): Logical connection name defined in the connections file.
  #                         When it is None,the connection parameters dictionary is used.
  # Returns:
  #   tuple[bool,str]: Success flag and error message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def OpenConnection(self,ConnectionName=None):

    #Exit if connection is already opened
    if self._ConnectionObj is not None and self._ConnectionName==ConnectionName:
      return True,""

    #Close existing connection if any
    if self._ConnectionObj is not None:
      self.CloseConnection()

    #Wait for library import
    Status,Message=self._ImportLibraries()
    if Status==False:
      return False,Message

    #Open connection
    try:
      with contextlib.redirect_stdout(io.StringIO()):
        if self._ConnParameters is not None:
          self._ConnectionObj=self._SnowflakeConnect(**self._ConnParameters,insecure_mode=True)
        else:
          self._ConnectionObj=self._SnowflakeConnect(connections_file_path=pathlib.Path(self._ConnectionsFile),connection_name=ConnectionName,insecure_mode=True)
      self._ConnectionName=ConnectionName
    except Exception as Ex:
      Message=f"Cannot open connection to Snowflake: {str(Ex)}"
      return False,Message

    #Return success
    return True,""

  # ----------------------------------------------------------------------------------------------------------------------
  # Close the current Snowflake connection if one is open.
  # ----------------------------------------------------------------------------------------------------------------------
  def CloseConnection(self):
    if self._ConnectionObj is None:
      return
    self._ConnectionObj.close()
    self._ConnectionObj=None
    self._ConnectionName=None

  # ----------------------------------------------------------------------------------------------------------------------
  # Get the name of the currently opened connection.
  # Returns:
  #   str | None: Connection name or None if no connection is open or disabled.
  # ----------------------------------------------------------------------------------------------------------------------
  def GetCurrentConnectionName(self):
    if self._ExecutionDisabled==False and self._ConnectionObj is not None:
      return self._ConnectionName
    else:
      return None

  # ----------------------------------------------------------------------------------------------------------------------
  # Run a SQL statement against the active Snowflake connection.
  # Args:
  #   Query (str | list[str]): SQL statement or list of SQL statements to execute.
  # Returns:
  #   tuple[bool,str,list[tuple] | None]: Success flag,message,and fetched results when successful.
  # ----------------------------------------------------------------------------------------------------------------------
  def ExecuteSqlQuery(self,Query):

    #Multi statement mode (when a list is passed)
    if isinstance(Query,list):
      AllResults=[]
      for SingleQuery in Query:
        Status,Message,Result=self.ExecuteSqlQuery(SingleQuery)
        if Status==False:
          return False,Message,None
        AllResults.extend(Result)
      return True,"",AllResults

    #Exit if execution is disabled
    if self._ExecutionDisabled==True:
      Message=f"Execution cancelled by user"
      return False,Message,None

    #Exit if connection was not opened before
    if self._ConnectionObj is None:
      Message=f"Snowflake connection is not open"
      return False,Message,None
    
    #Formatted query for debug output
    MinIndentation=min([len(Line) - len(Line.lstrip(" ")) for Line in Query.split("\n") if len(Line.lstrip(" "))!=0])
    DisplaySql="\n".join([(Line[MinIndentation:] if len(Line) > MinIndentation else "") for Line in Query.split("\n")])
    
    #Debug mode: shows SQL being executed and asks user to continue
    if self._Debug==True:
      print(f"\n\nAbout to execute SQL query:")
      print(DisplaySql)
      Answer=input(f"Continue: (y)es / (n)o / (a)ll / (c)ancel / (e)rrors only ? ")
      if Answer.lower()=="a":
        self._Debug=False
      elif Answer.lower()=="e":
        self._Debug=False
        self._DebugErrors=True
      elif Answer.lower()=="c":
        self._ExecutionDisabled=True
        print(f"Query execution: Cancelled")
        Message=f"Execution cancelled by user"
        return False,Message,None
      elif Answer.lower()!="y":
        print(f"Query execution: Skipped")
        Message=f"Execution skipped by user"
        return False,Message,None

    #Execute query
    try:
      Cursor=self._ConnectionObj.cursor()
      Cursor.execute(Query)
      Result=Cursor.fetchall()
      Metadata=Cursor.description
    except KeyboardInterrupt:
      Message=f"Interrupted by user"
      return False,Message,None
    except Exception as Ex:
      if self._DebugErrors==True:
        print(f"\n\n[ERROR] Execution of query failed: {str(Ex)}\n")
        print(DisplaySql)
      if self._Debug==True:
        print(f"[ERROR] Query execution failed: {str(Ex)}\n")
      Message=f"Execution error: {str(Ex)}"
      return False,Message,None

    #Print results in debug modes
    if self._Debug==True:
      print(f"[OK] Query executed ({len(Result)} row(s) returned)\n")
    
    #Convert rows into dictionaries
    ResultDict=[{Metadata[Index].name.lower(): Field for Index,Field in enumerate(Row)} for Row in Result]

    #Return results
    return True,"",ResultDict

  # ----------------------------------------------------------------------------------------------------------------------
  # Exposes the Snowflake split_statements utility.
  # Args:
  #   Script (str): SQL script to split.
  # Returns:
  #   list: List of statements.
  # ----------------------------------------------------------------------------------------------------------------------
  def SplitStatements(self,Script):
    Status,Message=self._ImportLibraries()
    if Status==False:
      return []
    return self._SnowflakeSplitStatements(io.StringIO(Script),remove_comments=True)

  # ----------------------------------------------------------------------------------------------------------------------
  # Execute a query and return raw results and metadata.
  # Args:
  #   Query (str): SQL query to execute.
  # Returns:
  #   tuple[bool,str,list[tuple] | None,list | None]: Success flag,message,fetched results,and metadata when successful.
  # ----------------------------------------------------------------------------------------------------------------------
  def ExecuteRawQuery(self,Query):
    if self._ConnectionObj is None:
      return False,"Snowflake connection is not open",None,None
    try:
      Cursor=self._ConnectionObj.cursor()
      Cursor.execute(Query)
      Result=Cursor.fetchall()
      Metadata=Cursor.description
      return True,"",Result,Metadata
    except Exception as Ex:
      return False,f"Execution error: {str(Ex)}",None,None
