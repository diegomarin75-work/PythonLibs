#Import libraries
import io
import tomllib
import pathlib
import threading
import contextlib

# -------------------------------------------------------------------------------------------------------------------
# SnowflakeManager encapsulates Snowflake connection helpers and background library preloading.
# -------------------------------------------------------------------------------------------------------------------
class SnowflakeManager:

  #Configuration constants
  PRELOAD_LIBRARIES_TIMEOUT_SECS=30

  # -----------------------------------------------------------------------------------------------------------------
  # This method initializes the SnowflakeManager with connection settings and optional library preloading.
  # Args:
  #   PreloadLibraries (bool): When True,Snowflake libraries are preloaded asynchronously.
  #   ConnectionsFile (str): Path to the Snowflake connections definition file.
  #   Debug (bool): When True,SQL queries are shown for confirmation before execution.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def __init__(self,PreloadLibraries=False,ConnectionsFile=None,Debug=False):

    #Save parameters as private instance attributes
    self._PreloadLibraries=PreloadLibraries
    self._ConnectionsFile=ConnectionsFile
    self._Debug=Debug
    self._ExecutionDisabled=False
    self._DebugErrors=False

    #Initialize library and connection state
    self._ImportLibrariesError=None
    self._LibrariesReady=None
    self._SnowflakeConnect=None
    self._SnowflakeSplitStatements=None
    self._ConnectionObj=None
    self._ConnectionName=None

    #Start asynchronous library preload when requested
    if PreloadLibraries==True:
      self._LibrariesReady=threading.Event()
      threading.Thread(target=self._ImportLibrariesDaemon,daemon=True).start()

  # -----------------------------------------------------------------------------------------------------------------
  # This private method loads Snowflake connector modules asynchronously and stores references.
  # Args:
  #   None
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def _ImportLibrariesDaemon(self):

    #Attempt to import Snowflake connector library and store function references
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

  # -----------------------------------------------------------------------------------------------------------------
  # This private method ensures Snowflake libraries are loaded,blocking until the daemon finishes.
  # Args:
  #   None
  # Returns:
  #   tuple: Success flag and diagnostic message on failure.
  # -----------------------------------------------------------------------------------------------------------------
  def _ImportLibraries(self):

    #Wait for daemon to finish if libraries are being preloaded
    if self._PreloadLibraries==True:
      self._LibrariesReady.wait(self.PRELOAD_LIBRARIES_TIMEOUT_SECS)
      if not self._LibrariesReady.is_set():
        Message="Snowflake libraries load timeout reached!"
        return False,Message

    #Import libraries again if preload failed or was not enabled
    if self._SnowflakeConnect is None:
      self._ImportLibrariesDaemon()

    #Check library load exception
    if self._ImportLibrariesError is not None:
      return False,self._ImportLibrariesError

    #Return success
    return True,""

  # -----------------------------------------------------------------------------------------------------------------
  # This method opens the configured Snowflake connection,reusing an existing one when possible.
  # Args:
  #   ConnectionName (str): Logical connection name in the connections file.
  # Returns:
  #   tuple: Success flag and error message on failure.
  # -----------------------------------------------------------------------------------------------------------------
  def OpenConnection(self,ConnectionName):

    #Exit if connection is already opened for the same connection name
    if self._ConnectionObj is not None and self._ConnectionName==ConnectionName:
      return True,""

    #Wait for library import to complete
    Status,Message=self._ImportLibraries()
    if Status==False:
      return False,Message

    #Open the Snowflake connection
    try:
      with contextlib.redirect_stdout(io.StringIO()):
        self._ConnectionObj=self._SnowflakeConnect(connections_file_path=pathlib.Path(self._ConnectionsFile),connection_name=ConnectionName)
      self._ConnectionName=ConnectionName
    except Exception as Ex:
      Message=f"Cannot open connection to Snowflake: {str(Ex)}"
      return False,Message

    #Return success
    return True,""

  # -----------------------------------------------------------------------------------------------------------------
  # This method closes the current Snowflake connection if one is open.
  # Args:
  #   None
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def CloseConnection(self):

    #Close connection and reset connection state
    if self._ConnectionObj is None:
      return
    self._ConnectionObj.close()
    self._ConnectionObj=None
    self._ConnectionName=None

  # -----------------------------------------------------------------------------------------------------------------
  # This method returns the name of the currently active Snowflake connection.
  # Args:
  #   None
  # Returns:
  #   str | None: Connection name,or None if no connection is open or execution is disabled.
  # -----------------------------------------------------------------------------------------------------------------
  def GetCurrentConnectionName(self):

    #Return connection name when execution is active and connection is open
    if self._ExecutionDisabled==False and self._ConnectionObj is not None:
      return self._ConnectionName
    else:
      return None

  # -----------------------------------------------------------------------------------------------------------------
  # This method runs a SQL statement or list of statements against the active Snowflake connection.
  # Args:
  #   Query (str | list): SQL statement or list of SQL statements to execute.
  # Returns:
  #   tuple: Success flag,message,and list of result dictionaries when successful.
  # -----------------------------------------------------------------------------------------------------------------
  def ExecuteSqlQuery(self,Query):

    #Multi-statement mode: recursively execute each statement in the list
    if isinstance(Query,list):
      AllResults=[]
      for SingleQuery in Query:
        Status,Message,Result=self.ExecuteSqlQuery(SingleQuery)
        if Status==False:
          return False,Message,None
        AllResults.extend(Result)
      return True,"",AllResults

    #Exit if execution was cancelled by user
    if self._ExecutionDisabled==True:
      Message="Execution cancelled by user"
      return False,Message,None

    #Exit if no connection is open
    if self._ConnectionObj is None:
      Message="Snowflake connection is not open"
      return False,Message,None

    #Format query for display by removing common leading indentation
    MinIndentation=min([len(Line)-len(Line.lstrip(" ")) for Line in Query.split("\n") if len(Line.lstrip(" ")) != 0])
    DisplaySql="\n".join([(Line[MinIndentation:] if len(Line) > MinIndentation else "") for Line in Query.split("\n")])

    #Debug mode: show SQL and prompt user to continue,skip,or cancel
    if self._Debug==True:
      print("\n\nAbout to execute SQL query:")
      print(DisplaySql)
      Answer=input("Continue: (y)es / (n)o / (a)ll / (c)ancel / (e)rrors only ? ")
      if Answer.lower()=="a":
        self._Debug=False
      elif Answer.lower()=="e":
        self._Debug=False
        self._DebugErrors=True
      elif Answer.lower()=="c":
        self._ExecutionDisabled=True
        print("Query execution: Cancelled")
        Message="Execution cancelled by user"
        return False,Message,None
      elif Answer.lower() != "y":
        print("Query execution: Skipped")
        Message="Execution skipped by user"
        return False,Message,None

    #Execute the query against the open connection
    try:
      Cursor=self._ConnectionObj.cursor()
      Cursor.execute(Query)
      Result=Cursor.fetchall()
      Metadata=Cursor.description
    except KeyboardInterrupt:
      Message="Interrupted by user"
      return False,Message,None
    except Exception as Ex:
      if self._DebugErrors==True:
        print(f"\n\n[FAIL] Execution of query failed: {str(Ex)}\n")
        print(DisplaySql)
      if self._Debug==True:
        print(f"[FAIL] Query execution failed: {str(Ex)}\n")
      Message=f"Execution error: {str(Ex)}"
      return False,Message,None

    #Print execution result in debug mode
    if self._Debug==True:
      print(f"[OK] Query executed ({len(Result)} row(s) returned)\n")

    #Convert result rows into dictionaries keyed by column name
    ResultDict=[{Metadata[Index].name.lower():Field for Index,Field in enumerate(Row)} for Row in Result]

    #Return success
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
