#Implement split statements inside daemon (library load time is significant)

#Import libraries
import io
import os
import sys
import json
import time
import pickle
import socket
import pathlib
import tempfile
import datetime
import argparse
import ctypes
import psutil
import subprocess
import traceback
import threading

#Constants
HOST="127.0.0.1"
RUN_STATE_FILE="sfd-run.dat"
DEBUG_LOG_FILE="sfd-log.txt"
DEBUG_MAX_LINES=5000
BUFFER_SIZE=65536
CONNECTION_BACKLOG=16
COMMAND_TIMEOUT_SECS=60*5
FREE_PORT_BEG=49152
FREE_PORT_END=65535
PING_OK_MESSAGE="PING_OK"
LAUNCH_DAEMON_WAIT_SECS=10
SF_CONN_FILE_VAR="SNOWFLAKE_CONN"
SF_HOME_FILE_VAR="SNOWFLAKE_HOME"

#Snowflake type codes
SNOWFLAKE_TYPE_CODES={0 :"int", 1 :"real", 2 :"string", 3 :"date", 4 :"timestamp", 5 :"variant", 6 :"timestamp_ltz", 7 :"timestamp_tz", 
                      8 :"timestamp_tz", 9 :"object", 10:"array", 11:"binary", 12:"time", 13:"boolean", 14:"geography", 15:"geometry", 16:"vector"  }

#Global thread lock for synchronizing access to shared resources
_ThreadLock=threading.Lock()

# ----------------------------------------------------------------------------------------------------------------------
# Class to handle daemon run state file
# ----------------------------------------------------------------------------------------------------------------------
class RunStateFile:

  # ----------------------------------------------------------------------------------------------------------------------
  # Class constructor
  # Args: None
  # Returns:
  # - str: Absolute temp file path
  # ----------------------------------------------------------------------------------------------------------------------
  def __init__(self):

    #Get path of run state file
    self._FileName=os.path.join(tempfile.gettempdir(),RUN_STATE_FILE)

  # ----------------------------------------------------------------------------------------------------------------------
  # Checl run state file exists
  # Args: None
  # Returns:
  # - bool: Success flag
  # ----------------------------------------------------------------------------------------------------------------------
  def Exists(self):
    return os.path.exists(self._FileName)

  # ----------------------------------------------------------------------------------------------------------------------
  # Read daemon runtime state JSON file
  # Args: None
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # - dict: Run file State Statistics
  # ----------------------------------------------------------------------------------------------------------------------
  def Read(self):
    try:
      with open(self._FileName,"r",encoding="utf-8") as FileObj:
        Stats=json.load(FileObj)
    except Exception as Ex:
      Message=f"Failure reading run state file: {str(Ex)}"
      return False,Message,None
    return True,"",Stats

  # ----------------------------------------------------------------------------------------------------------------------
  # Write daemon runtime state JSON file
  # (write is atomic operation, first write to a temp file and then rename to avoid partial writes)
  # Args: 
  # - Stats (dict): Run file State Statistics
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def Write(self,Stats):
    with _ThreadLock:
      try:
        TmpFile=self._FileName+".tmp"
        with open(TmpFile,"w",encoding="utf-8") as File:
          json.dump(Stats,File,indent=2)
        os.replace(TmpFile,self._FileName)
      except Exception as Ex:
        Message=f"Failure writing run state file: {str(Ex)}"
        return False,Message
      return True,""

  # ----------------------------------------------------------------------------------------------------------------------
  # Delete daemon temp files
  # Args: None
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def Delete(self):
    if os.path.exists(self._FileName):
      try:
        os.remove(self._FileName)
      except Exception:
        pass

# ---------------------------------------------------------------------------
# Debug log
# ---------------------------------------------------------------------------
class DebugLog:

  # -------------------------------------------------------------------------
  # Constructor
  # Args: None
  # Returns: None
  # -------------------------------------------------------------------------
  def __init__(self):
    
    #Initialize debug log
    self._DebugLogFile=os.path.join(tempfile.gettempdir(),DEBUG_LOG_FILE)
    self._MaxLines=DEBUG_MAX_LINES

    #Truncate log file if it exceeds max lines
    if self._DebugLogFile!=None and os.path.isfile(self._DebugLogFile):
      with open(self._DebugLogFile,"r",encoding="utf-8") as File:
        Lines=File.readlines()
      if len(Lines)>self._MaxLines:
        with open(self._DebugLogFile,"w",encoding="utf-8") as File:
          File.writelines(Lines[-self._MaxLines:])
    
    #Signal start in debug log
    self.Send("-"*120, Raw=True)

  # -------------------------------------------------------------------------
  # Append a timestamped debug message to the log file
  # Args:
  # - Message (string): Message to log
  # - Raw (bool): If True, write message as-is without timestamp or caller info
  # Returns: None
  # -------------------------------------------------------------------------
  def Send(self,Message,Raw=False):
      
    #Build message
    if Raw:
      Message=Message+"\n"
    else:
      Caller=traceback.extract_stack()[-2]
      CallerInfo=f"({os.path.basename(Caller.filename)}:{Caller.name}():{Caller.lineno})"
      TimeStamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      Message=f"[{TimeStamp}] {CallerInfo} {Message}\n"
    
    #Output message to console
    print(f"{Message}",end="",flush=True)
    
    #Append message to log file
    with _ThreadLock:
      if self._DebugLogFile!=None:
        with open(self._DebugLogFile,"a",encoding="utf-8") as File:
          File.write(Message)

# ----------------------------------------------------------------------------------------------------------------------
# Snowflake SQL daemon that keeps multiple connections open
# ----------------------------------------------------------------------------------------------------------------------
class SqlDaemon:

  # ----------------------------------------------------------------------------------------------------------------------
  # Initialize daemon state
  # Args:
  # - ConnectionsFile (str): Path to connections.toml file (optional)
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def __init__(self,ConnectionsFile=None):

    #Initialize state
    self._Port=None
    self._Pid=os.getpid()
    self._Terminate=False
    self._StartTime=datetime.datetime.now()
    self._TotalQueries=0
    self._ConnectionStatus={}
    self._Connections={}
    self._RunStateFile=RunStateFile()
    self._DebugLog=DebugLog()
    self._ConnectionsFile=ConnectionsFile

    #Get path of connections.toml file from environment variable if not provided
    if self ._ConnectionsFile is None:
      if os.environ.get(SF_CONN_FILE_VAR,None) is not None:
        self._ConnectionsFile=os.environ[SF_CONN_FILE_VAR]
      elif os.environ.get(SF_HOME_FILE_VAR,None) is not None:
        self._ConnectionsFile=os.path.join(os.environ[SF_HOME_FILE_VAR],"connections.toml")

    #Import snowflake connector lazily for daemon runtime only
    from snowflake.connector import connect
    self._SnowflakeConnect=connect

  # ----------------------------------------------------------------------------------------------------------------------
  # Compose daemon statistics object
  # Args: None
  # Returns:
  # - dict: Statistics snapshot
  # ----------------------------------------------------------------------------------------------------------------------
  def _FindFreePort(self):
    for Port in range(FREE_PORT_BEG,FREE_PORT_END+1):
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as Socket:
        try:
          Socket.bind((HOST,Port))
          self._Port=Port
          return True
        except OSError:
          continue
    return False

  # ----------------------------------------------------------------------------------------------------------------------
  # Compose daemon statistics object
  # Args: None
  # Returns:
  # - dict: Statistics snapshot
  # ----------------------------------------------------------------------------------------------------------------------
  def _GetStatistics(self):
    UptimeSecs=int((datetime.datetime.now()-self._StartTime).total_seconds())
    Stats={
      "pid":self._Pid,
      "port":self._Port,
      "open_connections":len(self._Connections),
      "total_queries":self._TotalQueries,
      "connection_status":self._ConnectionStatus,
      "start_time":self._StartTime.isoformat(),
      "updated_at":datetime.datetime.now().isoformat(),
      "uptime_seconds":UptimeSecs
    }
    return Stats

  # ----------------------------------------------------------------------------------------------------------------------
  # Persist latest daemon state into temp JSON file
  # Args: None
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def _UpdateRunStateFile(self):
    try:
      Stats=self._GetStatistics()
    except Exception as Ex:
      Message=f"Failed to get statistics for run state file: {str(Ex)}"
      return False,Message
    Status,Message=self._RunStateFile.Write(Stats)
    if Status==False:
      return False,Message
    return True,""

  # ----------------------------------------------------------------------------------------------------------------------
  # Opens connetion to snowflake (reuses connection if already opened)
  # Args:
  # - ConnectionName (str): Snowflake connection name from connections.toml
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def _OpenConnection(self,ConnectionName):

    #Get current timestamp for connection metadata
    CurrentTime=datetime.datetime.now().isoformat()
    
    #Get lock as we are accessing shared resources
    with _ThreadLock:

      #Reuse existing connection when already cached
      if ConnectionName in self._Connections:
        self._ConnectionStatus[ConnectionName]["last_used_at"]=CurrentTime
        return True,""

      #Error if connections file is not resolved
      if self._ConnectionsFile is None:
        Message="Cannot open connection, connections.toml file not provided or found in environment variables"
        return False,Message

      #Open and cache a new Snowflake connection
      try:
        Connection=self._SnowflakeConnect(connections_file_path=pathlib.Path(self._ConnectionsFile),connection_name=ConnectionName,insecure_mode=True)
        self._Connections[ConnectionName]=Connection
        CurrentTime=datetime.datetime.now().isoformat()
        self._ConnectionStatus[ConnectionName]={"opened_at":CurrentTime,"last_used_at":CurrentTime,"query_count":0}
      except Exception as Ex:
        Message=f"Cannot open connection to Snowflake for '{ConnectionName}': {str(Ex)}"
        return False,Message
    
    #Return success
    return True,""
    
  # ----------------------------------------------------------------------------------------------------------------------
  # Close all cached Snowflake connections
  # Args: None
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def _CloseAllConnections(self):
    for ConnectionName in self._Connections:
      try:
        self._Connections[ConnectionName].close()
      except Exception:
        pass
    self._Connections={}

  # ----------------------------------------------------------------------------------------------------------------------
  # Execute SQL on a connection and return rows as dictionaries
  # Args:
  # - ConnectionName (str): Connection name
  # - SqlQuery (str): SQL statement
  # - RawMode (bool): If True, return raw rows instead of dictionaries
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # - list of dict: List of rows as dictionaries
  # - list of tuple: Metadata for each column
  # ----------------------------------------------------------------------------------------------------------------------
  def _ExecuteQuery(self,ConnectionName,SqlQuery,RawMode):

    #Open connection if needed before executing query
    Status,Message=self._OpenConnection(ConnectionName)
    if Status==False:
      return False,Message,None,None

    #Run SQL and fetch rows with metadata
    try:
      Cursor=self._Connections[ConnectionName].cursor()
      Cursor.execute(SqlQuery)
      Rows=Cursor.fetchall()
      MetaData=Cursor.description
    except Exception as Ex:
      return False,f"{str(Ex)}",None,None

    #Convert fetched rows to lower-case column dictionaries
    if RawMode==True:
      Result=Rows
    else:
      Result=[]
      for Row in Rows:
        ResultRow={MetaData[Index].name.lower():Field for Index,Field in enumerate(Row)}
        Result.append(ResultRow)

    #Get column metadata
    if RawMode==True:
      Columns=MetaData
    else:
      Columns=[]
      for Column in MetaData:
        Name=str(Column.name)
        TypeName=(SNOWFLAKE_TYPE_CODES[Column.type_code] if Column.type_code in SNOWFLAKE_TYPE_CODES else "unknown")
        DisplaySize=Column.display_size
        InternalSize=Column.internal_size
        Precision=Column.precision
        Scale=Column.scale
        Nullable=Column.is_nullable
        Columns.append({"name":Name,"type":TypeName,"display_size":DisplaySize,"internal_size":InternalSize,"precision":Precision,"scale":Scale,"nullable":Nullable})

    #Update counters after successful execution
    with _ThreadLock:
      self._TotalQueries+=1
      self._ConnectionStatus[ConnectionName]["query_count"]+=1

    #Return successful query result
    return True,"",Result,Columns
  
  # ----------------------------------------------------------------------------------------------------------------------
  # Get requeest data from socket
  # Args:
  # - SocketConnection (socket.socket): Socket connection object
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # - dict: Request payload
  # - int: Number of bytes read from socket
  # ----------------------------------------------------------------------------------------------------------------------
  def _GetSocketRequest(self,SocketConnection):
    
    #Read request as pickle payload from socket
    try:
      Bytes=[]
      while True:
        Data=SocketConnection.recv(BUFFER_SIZE)
        if not Data:
          break
        Bytes.append(Data)
        if len(Data)<BUFFER_SIZE:
          break
      if len(Bytes)==0:
        RequestBytes=b""
      RequestBytes=b"".join(Bytes)
      Request=pickle.loads(RequestBytes)
    except Exception as Ex:
      Message=f"Exception reading request from socket: {str(Ex)}"
      return False,Message,None,None
    
    #Return request
    return True,"",Request,len(RequestBytes)

  # ----------------------------------------------------------------------------------------------------------------------
  # Process incoming daemon command and return response
  # Args:
  # - Command (str): Command name
  # - Request (dict): JSON request object
  # - SocketConnection (socket.socket): Socket connection object
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def _ExecuteCommand(self,Command,Request,SocketConnection):

    #Catch exceptions
    try:
    
      #Debug message for command execution
      self._DebugLog.Send(f"Executing command '{Command}' ...")
      
      #Handle ping command
      if Command=="ping":
        Result={"status":True,"message":PING_OK_MESSAGE}

      #Handle SQL query request
      elif Command=="query":
        if "sql" not in Request or "con" not in Request or "raw" not in Request:
          Message="Missing parameters for query command, expected 'sql', 'con' and 'raw'"
          Result={"status":False,"message":Message}
        else:
          Status,Message,QueryResult,Columns=self._ExecuteQuery(Request["con"],Request["sql"],Request["raw"])
          if Status==False:
            Result={"status":False,"message":Message}
          else:
            Result={"status":True,"message":"","result":QueryResult,"columns":Columns}
      
      #Handle status request and return statistics
      elif Command=="status":
        Result={"status":True,"message":"","statistics":self._GetStatistics()}

      #Handle daemon termination request
      elif Command=="terminate":
        self._Terminate=True
        Result={"status":True,"message":"Termination signal received"}

      #Invalid command
      else:
        Message=f"Invalid command: {Command}"
        Result={"status":False,"message":Message}
      
      #Inform about command execution
      if Result["status"]==True:
        self._DebugLog.Send(f"Command '{Command}' executed successfully")
      else:
        self._DebugLog.Send(f"Command '{Command}' failed: {Result['message']}")
      
      #Update run state file after command execution
      Status,Message=self._UpdateRunStateFile()
      if Status==False:
        self._DebugLog.Send(f"{Message}")
    
    #Exception handling for command execution
    except Exception as Ex:
      Message=f"Exception executing command '{Request.get('command','unknown')}': {str(Ex)}"
      Result={"status":False,"message":Message}
    
    #Send response through socket as pickle payload
    try:
      Bytes=pickle.dumps(Result,protocol=pickle.HIGHEST_PROTOCOL)
      SocketConnection.sendall(Bytes)
      self._DebugLog.Send(f"Sent response to {SocketConnection.getpeername()}")
    except Exception as Ex:
      SocketConnection.close()
      Message=f"Failed to send response: {str(Ex)}"
      self._DebugLog.Send(f"{Message}")
      return

    #Close socket connection after processing request
    SocketConnection.close()
  
  # ----------------------------------------------------------------------------------------------------------------------
  # Run daemon socket loop until terminate command arrives
  # Args: None
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def Listen(self):

    #Stat messae
    self._DebugLog.Send(f"Starting SQL daemon (pid={self._Pid}) ...")
    
    #Find free port to listen on
    if self._FindFreePort()==False:
      self._DebugLog.Send(f"Cannot find free port to listen on")
      return False

    #Persist initial state file before entering socket loop
    Status,Message=self._UpdateRunStateFile()
    if Status==False:
      self._DebugLog.Send(f"{Message}")
      return False
    
    #Open listening socket and process incoming requests
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as Socket:
      Socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
      Socket.bind((HOST,self._Port))
      Socket.listen(CONNECTION_BACKLOG)
      self._DebugLog.Send(f"Listening on port {self._Port} (pid={self._Pid})")

      #Keep serving requests until termination flag is set
      while self._Terminate==False:

        #Accept one incoming client connection
        try:
          self._DebugLog.Send(f"Waiting for incoming connection...")
          SocketConnection,Address=Socket.accept()
          self._DebugLog.Send(f"Accepted connection from {Address[0]}:{Address[1]}")
        except Exception:
          continue

        #Get request as pickle payload
        Status,Message,Request,RequestLen=self._GetSocketRequest(SocketConnection)
        if Status==False:
          SocketConnection.close()
          self._DebugLog.Send(f"{Message}")
          continue
        self._DebugLog.Send(f"Received request of {RequestLen} bytes from {Address[0]}:{Address[1]}")

        #Validate command field in request
        if "command" not in Request:
          SocketConnection.close()
          Message="Invalid request, missing command"
          self._DebugLog.Send(f"{Message}")
          continue
        Command=Request["command"]

        #Execute command (if command is SQL query, it will be executed in a separate thread to avoid blocking the socket loop)
        if Command=="query":
          Thread=threading.Thread(target=self._ExecuteCommand,args=(Command,Request,SocketConnection))
          self._DebugLog.Send(f"Executing SQL query command in a separate thread {Thread.name} ...")
          Thread.start()
        else:
          self._ExecuteCommand(Command,Request,SocketConnection)
        
    #Close all connections
    self._DebugLog.Send(f"Closing all connections")
    self._CloseAllConnections()

    #Cleanup files on exit
    self._DebugLog.Send(f"Cleaning up temp files")
    self._RunStateFile.Delete()
    
    #Terminate
    self._DebugLog.Send(f"Terminating")
    return True

# ----------------------------------------------------------------------------------------------------------------------
# Snowflake SQL cient
# ----------------------------------------------------------------------------------------------------------------------
class SqlClient:

  # ----------------------------------------------------------------------------------------------------------------------
  # Initialize daemon state
  # Args:
  # - ConnectionsFile (str): Path to connections.toml file (optional)
  # - Debug (bool): If True, enable debug mode
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def __init__(self,ConnectionsFile=None,Debug=False):
    
    #Initialize state
    self._Port=None
    self._ConnectionName=None
    self._ConnectionsFile=ConnectionsFile
    self._Debug=Debug
    self._DebugErrors=False
    self._ExecutionDisabled=False
    self._RunStateFile=RunStateFile()

    #Get path of connections.toml file from environment variable if not provided
    if self._ConnectionsFile is None and os.environ.get(SF_CONN_FILE_VAR,None) is not None:
      self._ConnectionsFile=os.environ[SF_CONN_FILE_VAR]
    elif self._ConnectionsFile is None and os.environ.get(SF_HOME_FILE_VAR,None) is not None:
      self._ConnectionsFile=os.path.join(os.environ[SF_HOME_FILE_VAR],"connections.toml")
    else:
      self._ConnectionsFile=None

  # ----------------------------------------------------------------------------------------------------------------------
  # Check whether a process id is currently running on Windows.
  # Args:
  # - Pid (int): Process id to validate.
  # Returns:
  # - bool: True when process exists.
  # ----------------------------------------------------------------------------------------------------------------------
  def _IsProcessRunning(self,Pid):
    try:
      ProcessQueryLimitedInformation=0x1000
      Handle=ctypes.windll.kernel32.OpenProcess(ProcessQueryLimitedInformation,False,Pid)
      if Handle==0:
        return False
      ctypes.windll.kernel32.CloseHandle(Handle)
      return True
    except Exception:
      return False

  # ----------------------------------------------------------------------------------------------------------------------
  # Kills Sql daemon (if running)
  # Args:
  # - Port (int): Socket port to listen on
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def _KillSqlDaemon(self):

    #Finds any process by command line like "python *\sfd.py" and kills it
    for Process in psutil.process_iter():
      try:
        CmdLine=Process.cmdline()
        if len(CmdLine)>1 and CmdLine[0].endswith("python.exe") and CmdLine[1].endswith("sfd.py"):
          Process.kill()
          time.sleep(1)
      except Exception:
        pass

  # ----------------------------------------------------------------------------------------------------------------------
  # Launch Sql daemon
  # Args: None
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def _LaunchSqlDaemon(self):

    #Launch a new daemon process
    try:
      CreationFlags=0x00000008 #CREATE_NO_WINDOW
      Arguments=[sys.executable,__file__,"--run"]
      if self._ConnectionsFile is not None:
        Arguments+=["--conn-file",self._ConnectionsFile]
      Process=subprocess.Popen(Arguments,creationflags=CreationFlags)
    except Exception as Ex:
      Message=f"Cannot launch SQL daemon: {str(Ex)}"
      return False,Message

    #Wait for daemon to start and write run state file
    for _ in range(LAUNCH_DAEMON_WAIT_SECS):
      time.sleep(1)
      Status,Message,Stats=self._RunStateFile.Read()
      if Status==True and Stats is not None and "port" in Stats:
        return True,""

    #Daemon did not start in time
    Message="SQL daemon did not start in time"
    return False,Message

  # ----------------------------------------------------------------------------------------------------------------------
  # Sends a command to the daemon socket and returns the response
  # Args:
  # - Port (int): Daemon socket port
  # - Payload (dict): Command payload
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # - dict: Response payload
  # ----------------------------------------------------------------------------------------------------------------------
  def _SendCommand(self,Payload):

    #Open socket,send request and receive response
    try:
      RequestBytes=pickle.dumps(Payload,protocol=pickle.HIGHEST_PROTOCOL)
      with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as Sckt:
        Sckt.settimeout(COMMAND_TIMEOUT_SECS)
        Sckt.connect((HOST,int(self._Port)))
        Sckt.sendall(RequestBytes)
        Chunks=[]
        while True:
          Data=Sckt.recv(BUFFER_SIZE)
          if not Data:
            break
          Chunks.append(Data)
    except Exception as Ex:
      return False,f"Socket communication failed: {str(Ex)}",None

    #Parse response pickle
    try:
      Response=pickle.loads(b"".join(Chunks))
    except Exception as Ex:
      return False,f"Invalid response from daemon: {str(Ex)}",None

    #Return parsed response
    return True,"",Response

  # ----------------------------------------------------------------------------------------------------------------------
  # Get Sql daemon (locate already running daemon or launch a new one)
  # Args:
  #   RelaunchOnError (bool): Whether to relaunch daemon if it is not running or has errors
  # Returns:
  #   bool: Success flag
  #   str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def _GetSqlDaemon(self,RelaunchOnError=True):

    #Read run state file (kill and launch daemon on error)
    Status,Message,Stats=self._RunStateFile.Read()
    if Status==False:
      if RelaunchOnError==False:
        return False,Message
      self._KillSqlDaemon()
      Status,Message=self._LaunchSqlDaemon()
      if Status==False:
        return False,Message
      Status,Message,Stats=self._RunStateFile.Read()
      if Status==False:
        Message="Unable to launch SQL daemon"
        return False,Message

    #Check daemon process is running (kill and launch daemon on error)
    Pid=Stats["pid"]
    if self._IsProcessRunning(Pid)==False:
      if RelaunchOnError==False:
        return False,"SQL Daemon process not running"
      self._KillSqlDaemon()
      Status,Message=self._LaunchSqlDaemon()
      if Status==False:
        return False,Message
      Status,Message,Stats=self._RunStateFile.Read()
      if Status==False:
        Message="Unable to launch SQL daemon"
        return False,Message
    
    #Check stats contains a valid port number
    self._Port=Stats.get("port",None)
    if self._Port is None or not isinstance(self._Port,int) or self._Port<FREE_PORT_BEG or self._Port>FREE_PORT_END:
      Message="SQL daemon run state file does not contain port number or port number is invalid!"
      return False,Message

    #Test daemon with ping command
    Status,Messsage,Response=self._SendCommand({"command":"ping"})
    if Status==False:
      Message=f"Daemon test failed: {Message}"
      return None
    ResponseStatus=Response.get("status",False)
    ResponseMessage=Response.get("message",None)
    if ResponseStatus!=True or ResponseMessage!=PING_OK_MESSAGE:
      Message=f"Daemon ping test failed: {ResponseMessage}"
      return False,Message
    
    #Return success
    return True,""

  # ----------------------------------------------------------------------------------------------------------------------
  # Wakeup daemon (launch if not running)
  # Args: None
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # ----------------------------------------------------------------------------------------------------------------------
  def WakeUp(self):

    #Ensure daemon is running
    Status,Message=self._GetSqlDaemon()
    if Status==False:
      Message=f"Cannot get SQL daemon: {Message}"
      return False,Message
    
    #Get daemon statistics
    Status,Message,Stats=self._RunStateFile.Read()
    if Status==False:
      Message=f"Cannot read SQL daemon run state file: {Message}"
      return False,Message
    
    #Inform about daemon status
    print(f"SQL daemon is running (pid={Stats['pid']}, port={Stats['port']}, uptime={Stats['uptime_seconds']}s, connections={Stats['open_connections']}, queries={Stats['total_queries']})")
    
    #Return success
    return True,""
    
  # ----------------------------------------------------------------------------------------------------------------------
  # Sets default connections to execute SQL queries
  # Args:
  # - ConnectionName (str): Snowflake connection name
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def SetConnection(self,ConnectionName):
    self._ConnectionName=ConnectionName

  # ----------------------------------------------------------------------------------------------------------------------
  # Forgets current connection
  # Args: None
  # Returns: None
  # ----------------------------------------------------------------------------------------------------------------------
  def ForgetConnection(self):
    self._ConnectionName=None

  # ----------------------------------------------------------------------------------------------------------------------
  # Execute SQL query on client
  # Args:
  # - SqlQuery (str): SQL statement
  # - RawMode (bool): If True, return raw rows instead of dictionaries
  # Returns:
  # - bool: Success flag
  # - str: Message in case of error
  # - list of dict: List of rows as dictionaries
  # - list of tuple: Metadata for each column
  # ----------------------------------------------------------------------------------------------------------------------
  def ExecuteSqlQuery(self,SqlQuery,RawMode=False):

    #Exit if execution was cancelled by user
    if self._ExecutionDisabled==True:
      Message="Execution cancelled by user"
      return False,Message,None,None

    #Ensure connection name is set
    if self._ConnectionName is None:
      Message="Connection not set, use SetConnection() to set a connection name before executing SQL queries"
      return False,Message,None,None

    #Ensure daemon is running
    Status,Message=self._GetSqlDaemon()
    if Status==False:
      Message=f"Cannot get SQL daemon: {Message}"
      return False,Message,None,None
    
    #Format query for display by removing common leading indentation
    MinIndentation=min([len(Line)-len(Line.lstrip(" ")) for Line in SqlQuery.split("\n") if len(Line.lstrip(" "))!=0])
    DisplaySql="\n".join([(Line[MinIndentation:] if len(Line) > MinIndentation else "") for Line in SqlQuery.split("\n")])

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
      elif Answer.lower()!="y":
        print("Query execution: Skipped")
        Message="Execution skipped by user"
        return False,Message,None,None

    #Send query command to daemon and parse response.
    Status,Message,Response=self._SendCommand({"command":"query","sql":SqlQuery,"con":self._ConnectionName,"raw":RawMode})
    if Status==False:
      Message=f"Cannot execute query on SQL daemon: {Message}"
      return False,Message,None,None

    #Get response fields
    Status=Response.get("status",False)
    Message=Response.get("message","Unable to get message from SQL daemon response")
    Result=Response.get("result",None)
    Columns=Response.get("columns",None)

    #Return error when daemon returned an error
    if Status==False:
      if self._DebugErrors==True:
        print(f"\n\n[FAIL] Execution of query failed: {Message}\n")
        print(DisplaySql)
      if self._Debug==True:
        print(f"[FAIL] Query execution failed: {Message}\n")
      Message=f"Execution error: {Message}"
      return False,Message,None,None

    #Print execution result in debug mode
    if self._Debug==True:
      print(f"[OK] Query executed ({len(Result)} row(s) returned)\n")
  
    #Return successful query result
    return True,"",Result,Columns

  # ----------------------------------------------------------------------------------------------------------------------
  # Exposes the Snowflake split_statements utility.
  # Args:
  #   Script (str): SQL script to split.
  # Returns:
  #   list: List of statements.
  # ----------------------------------------------------------------------------------------------------------------------
  def SplitStatements(self,Script):
    from snowflake.connector.util_text import split_statements
    return split_statements(io.StringIO(Script),remove_comments=True)

  # ----------------------------------------------------------------------------------------------------------------------
  # Get SQL daemon statistics
  # Args: None
  # Returns:
  # ----------------------------------------------------------------------------------------------------------------------
  def GetStats(self):

    #Check if run state file exists (if not, daemon is not running)
    if self._RunStateFile.Exists()==False:
      Message="SQL daemon not running (run state file not found)"
      return False,Message,None
    
    #Get daemon instance
    Status,Message=self._GetSqlDaemon(RelaunchOnError=False)
    if Status==False:
      return False,Message,None

    #Send status command to daemon and parse response
    Status,Message,Response=self._SendCommand({"command":"status"})
    if Status==False:
      Message=f"Cannot get status from SQL daemon: {Message}"
      return False,Message,None
    
    #Get response fields
    Status=Response.get("status",False)
    Message=Response.get("message","Unable to get message from SQL daemon response")
    Stats=Response.get("statistics",None)

    #Return error when daemon returned an error
    if Status==False:
      Message=f"on SQL daemon status: {Message}"
      return False,Message,None

    #Return successful statistics result
    return True,"",Stats

  # ----------------------------------------------------------------------------------------------------------------------
  # Stop daemon
  # ----------------------------------------------------------------------------------------------------------------------
  def Stop(self):

    #Try to get running daemon instance
    Status,Message=self._GetSqlDaemon(RelaunchOnError=False)
    
    #If running send stop command (and forcefully kill daemon if it does not respond)
    if Status==True:
      Status,Message,Response=self._SendCommand({"command":"terminate"})
      if Status==False:
        self._KillSqlDaemon()
        return f"Daemon forcefully terminated, did not respond to terminate command: {Message}"
      if Response.get("status",False)!=True:
        self._KillSqlDaemon()
        return f"Daemon forcefully terminated, terminate command failed: {Response.get('message','Unknown error')}"
      return "SQL daemon terminated successfully"
    
    #If appears not running, forcefully kill any remaining process
    self._KillSqlDaemon()
    return f"SQL daemon appears not running, forceful termination launched anyway"

# ----------------------------------------------------------------------------------------------------------------------
# Build argparse parser for command line options.
# Args: None
# Returns:
# - argparse.ArgumentParser: Configured parser.
# ----------------------------------------------------------------------------------------------------------------------
def BuildArgumentParser():

  #Build parser with explicit operation flags.
  Parser=argparse.ArgumentParser(prog="sfd.py",description="Snowflake SQL Daemon",formatter_class=argparse.RawTextHelpFormatter,add_help=False)
  RunGroup=Parser.add_mutually_exclusive_group()
  RunGroup.add_argument("--run",dest="Run",action="store_true",help="Start daemon and listen for socket commands")
  RunGroup.add_argument("--wakeup",dest="WakeUp",action="store_true",help="Wakeup daemon (launch if not running)")
  RunGroup.add_argument("--status",dest="Status",action="store_true",help="Get daemon status and statistics")
  RunGroup.add_argument("--stop",dest="Stop",action="store_true",help="Stop daemon")
  Parser.add_argument("--conn-file",dest="ConnFile",type=str,help="Path to connections.toml file (optional)",default=None)
  return Parser

# ----------------------------------------------------------------------------------------------------------------------
# Parse command line arguments.
# Args:
#   Args (list[str]): Arguments excluding script path.
# Returns:
#   tuple[bool,str,dict|None]: Success flag,message,and options dictionary.
# ----------------------------------------------------------------------------------------------------------------------
def ParseArguments():

  #Return help mode when no arguments are given.
  if len(sys.argv)==1:
    return True,"",{"run_mode":"help"}

  #Parse with argparse.
  Parser=BuildArgumentParser()
  try:
    Args=Parser.parse_args(sys.argv[1:])
  except SystemExit:
    return False,"",None

  #Ensure exactly one mode is selected.
  ModeFlags={"run":Args.Run,"wakeup":Args.WakeUp,"status":Args.Status,"stop":Args.Stop}
  SelectedMode=[ModeName for ModeName,Enabled in ModeFlags.items() if Enabled==True]
  if len(SelectedMode)!=1:
    return False,"One and only one mode must be passed: --run, --wakeup, --status or --stop",None
  RunMode=SelectedMode[0]

  #Get options as dictionary
  Options={"run_mode":RunMode,"conn_file":Args.ConnFile}

  #Return normalized options contract.
  return True,"",Options

# ----------------------------------------------------------------------------------------------------------------------
# Program entry point.
# Args: None
# Returns:
#   int: Process exit code.
# ----------------------------------------------------------------------------------------------------------------------
def Main():

  #Parse command line options and validate arguments.
  Status,Message,Options=ParseArguments()
  if Status==False:
    if Message is not None and len(Message)!=0:
      print(Message)
    return 1

  #Show help when no mode was requested.
  if Options["run_mode"]=="help":
    BuildArgumentParser().print_help()
    return 0

  #Run daemon loop mode.
  elif Options["run_mode"]=="run":
    ConnectionsFile=Options["conn_file"]
    if ConnectionsFile is None:
      print("Option --conn-file required for --run mode")
      return 1
    SqlDaemonInstance=SqlDaemon(ConnectionsFile=ConnectionsFile)
    Status=SqlDaemonInstance.Listen()
    if Status==False:
      return 1

  #Wakeup daemon
  elif Options["run_mode"]=="wakeup":
    ConnectionsFile=Options["conn_file"]
    SqlClientInstance=SqlClient(ConnectionsFile=ConnectionsFile)
    Status,Message=SqlClientInstance.WakeUp()
    if Status==False:
      print(Message)
      return 1

  #Run status query mode.
  elif Options["run_mode"]=="status":
    SqlClientInstance=SqlClient()
    Status,Message,Stats=SqlClientInstance.GetStats()
    if Status==False:
      print(Message)
      return 1
    print(json.dumps(Stats,indent=2))

  #Run stop mode.
  elif Options["run_mode"]=="stop":
    SqlClientInstance=SqlClient()
    Message=SqlClientInstance.Stop()
    print(Message)

  #Return invalid mode error
  else:
    print("Invalid run mode")
    return 1
  
  #Return success exit code
  return 0

# ----------------------------------------------------------------------------------------------------------------------
# Execute main entry point when script is started directly.
# ----------------------------------------------------------------------------------------------------------------------
if __name__=="__main__":
  sys.exit(Main())