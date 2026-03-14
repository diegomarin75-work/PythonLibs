#Import libraries
import os
import json
import chardet
import subprocess
from pathlib import Path

# ----------------------------------------------------------------------------------------------------------------------
# Reads the tool version from the VERSION file.
# ----------------------------------------------------------------------------------------------------------------------
def GetVersion():
  try:
    Version=(Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
  except Exception:
    Version="0.0.0"
  return Version

# ----------------------------------------------------------------------------------------------------------------------
# Helper function coalesce.
# Args:
#   *Args: List of arguments to evaluate.
# Returns:
#   First argument that is not None,or None if all are None.
# ----------------------------------------------------------------------------------------------------------------------
def Coalesce(*Args):
  for Arg in Args:
    if Arg is not None:
        return Arg
  return None

# ----------------------------------------------------------------------------------
# Format seconds as a human readable string.
# Args:
#   TotalSecs (integer): Total number of seconds.
# Returns:
#   str: Formatted time string.
# ----------------------------------------------------------------------------------------------------------------------
def FormatSeconds(TotalSecs):
  Hours=int(TotalSecs // 3600)
  Minutes=int((TotalSecs % 3600) // 60)
  Secs=TotalSecs % 60
  TimeParts=[]
  if Hours>0:
    TimeParts.append("{hrs}h".format(hrs=Hours))
  if Minutes>0 or Hours>0:
    TimeParts.append("{mins}m".format(mins=Minutes))
  TimeParts.append("{sec:.2f}s".format(sec=Secs))
  return " ".join(TimeParts)

# ----------------------------------------------------------------------------------
# Convert a path to an absolute,normalized form.
# Args:
#   FilePath (str): Input path that may be relative.
#   RelativeTo (str | None): When provided,relative paths are considered relative to this path.
# Returns:
#   str: Normalized absolute path with lowercase drive letters on Windows.
# ----------------------------------------------------------------------------------------------------------------------
def AbsPath(FilePath,RelativeTo=None):
  if RelativeTo is not None:
    AbsFilePath=os.path.normpath(os.path.join(RelativeTo,FilePath))
  else:
    AbsFilePath=os.path.normpath(os.path.abspath(FilePath))
  if len(AbsFilePath)>=2 and AbsFilePath[0].lower()>="a" and AbsFilePath[0].lower()<="z" and AbsFilePath[1]==":":
    AbsFilePath=AbsFilePath[0].lower() + AbsFilePath[1:]
  return AbsFilePath

# ---------------------------------------------------------------------------------------------------------------------
# Execute a shell command,capturing combined stdout/stderr text.
# Args:
#   Command (str): Command line to execute via the system shell.
# Returns:
#   tuple[int,str]: Process return code plus captured output text.
# ----------------------------------------------------------------------------------------------------------------------
def ExecCommand(Command):
  Proc=subprocess.Popen(Command,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8")
  Output,Unused=Proc.communicate()
  RetCode=Proc.returncode
  return RetCode,Output

# ---------------------------------------------------------------------------------------------------------------------
# Gets the root path of a Git repository from a given path inside the repo.
# Args:
#   GitRepo (str): Candidate path to test.
# Returns:
#   str | None: Absolute path of the Git repository root,or None when the path is not inside a Git repository.
# ----------------------------------------------------------------------------------------------------------------------
def GetGitRepoRoot(GitRepo):
  RetCode,Output=ExecCommand(f"git -C {GitRepo} rev-parse --show-toplevel")
  if RetCode != 0:
    return None
  else:
    return AbsPath(Output.strip())

# ---------------------------------------------------------------------------------------------------------------------
# Verify that the supplied path points to a Git repository root or subdirectory.
# Args:
#   GitRepo (str): Candidate path to test.
# Returns:
#   bool: True when Git identifies the path,otherwise False.
# ----------------------------------------------------------------------------------------------------------------------
def IsGitRepo(GitRepo):
  RetCode,Unused=ExecCommand(f"git -C {GitRepo} rev-parse --show-toplevel")
  if RetCode != 0:
    return False
  else:
    return True

# ---------------------------------------------------------------------------------------------------------------------
# Checks whether a file exists on a Git repo branch.
# Args:
#   RepoPath (str): Git repository path.
#   BranchName (str): Branch name.
#   FilePath (str): File path relative to the repository root.
# Returns:
#   bool: True when file exists on branch,otherwise False.
# ----------------------------------------------------------------------------------------------------------------------
def IsFileOnBranch(RepoPath,BranchName,FilePath):
  RetCode,Unused=ExecCommand(f"git -C {RepoPath} cat-file -e origin/{BranchName}:{FilePath.replace(os.sep,'/')}")
  if RetCode==0:
    return True
  else:
    return False

# ---------------------------------------------------------------------------------------------------------------------
# Guess a file's text encoding using the chardet heuristic.
# Args:
#   FilePath (str): File whose encoding should be detected.
#   NumBytes (int): Number of bytes to sample from the file.
# Returns:
#   tuple[bool,str,str | None]: Success flag,message,and detected encoding when available.
# ----------------------------------------------------------------------------------------------------------------------
def DetectFileEncoding(FilePath,NumBytes=100000):

  #Read sample bytes from file
  try:
    FileHnd=open(FilePath,"rb")
    RawData=FileHnd.read(NumBytes)
    FileHnd.close()
  except Exception as Ex:
    Message=f"Unable to detect file encoding: {str(Ex)}"
    return False,Message,None

  #Guess encoding
  try:
    FileEncoding=chardet.detect(RawData)["encoding"]
  except Exception as Ex:
    Message=f"Unable to detect file encoding: {str(Ex)}"
    return False,Message,None

  #Return result
  return True,"",FileEncoding

# ----------------------------------------------------------------------------------
# Load a JSON configuration file that tolerates // comments and multiline strings.
# Args:
#   FilePath (str): Path to the JSON configuration file.
# Returns:
#   tuple[bool,str,dict | None]: Success flag,diagnostic message,and parsed JSON object.
# ----------------------------------------------------------------------------------------------------------------------
def JsonFileParser(FilePath):

  # ----------------------------------------------------------------------------------------------------------------------
  # Replaces new lines inside strings as \n (as standard JSON requires).
  # ----------------------------------------------------------------------------------------------------------------------
  def FixMultilineJson(Content):
    Output=[]
    StringMode=False
    EscapeMode=False
    for Char in Content:
      if StringMode:
        if EscapeMode:
          Output.append(Char)
          EscapeMode=False
        elif Char=="\\":
          Output.append(Char)
          EscapeMode=True
        elif Char=='"':
          Output.append(Char)
          StringMode=False
        elif Char=="\n":
          Output.append("\\n")
        else:
          Output.append(Char)
      else:
        if Char=='"':
          Output.append(Char)
          StringMode=True
        else:
          Output.append(Char)
    return "".join(Output)

  #Load JSON file
  #(comment lines are replaced with empty lines to preserve line numbering for error messages)
  try:
    FileHnd=open(FilePath,"r",encoding="utf-8")
    FileContent=FileHnd.read()
    FileHnd.close()
    FileContent="\n".join([(Line if Line.strip().startswith("//")==False else "") for Line in FileContent.split("\n")])
    FileContent=FixMultilineJson(FileContent)
    JsonObj=json.loads(FileContent)
  except Exception as Ex:
    Message=f"Exception reading configuration file ({FilePath}): {str(Ex)}"
    return False,Message,None

  #Return result
  return True,"",JsonObj