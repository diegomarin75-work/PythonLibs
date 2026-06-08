#Import libraries
import os
import re
import sys

# ---------------------------------------------------------------------------------------------------------------------
# Printing library with console formatting capabilities
# ---------------------------------------------------------------------------------------------------------------------
class PrintingLibrary:

  #Private constants
  _SEPARATOR_ID="$SEP$"
  _WHEEL_CHARS=["-","\\","|","/"]

  #Ansi colors (fmt: off)
  ANSI_ESCAPE_PREFIX="\033["
  ANSI_FD_BLACK  =30; ANSI_BD_BLACK  =40; ANSI_FB_BLACK  =90; ANSI_BB_BLACK  =100;
  ANSI_FD_RED    =31; ANSI_BD_RED    =41; ANSI_FB_RED    =91; ANSI_BB_RED    =101;
  ANSI_FD_GREEN  =32; ANSI_BD_GREEN  =42; ANSI_FB_GREEN  =92; ANSI_BB_GREEN  =102;
  ANSI_FD_YELLOW =33; ANSI_BD_YELLOW =43; ANSI_FB_YELLOW =93; ANSI_BB_YELLOW =103;
  ANSI_FD_BLUE   =34; ANSI_BD_BLUE   =44; ANSI_FB_BLUE   =94; ANSI_BB_BLUE   =104;
  ANSI_FD_MAGENTA=35; ANSI_BD_MAGENTA=45; ANSI_FB_MAGENTA=95; ANSI_BB_MAGENTA=105;
  ANSI_FD_CYAN   =36; ANSI_BD_CYAN   =46; ANSI_FB_CYAN   =96; ANSI_BB_CYAN   =106;
  ANSI_FD_WHITE  =37; ANSI_BD_WHITE  =47; ANSI_FB_WHITE  =97; ANSI_BB_WHITE  =107;

  # ----------------------------------------------------------------------------------------------------------------------
  # Class constructor: Initializes all class variables
  # ----------------------------------------------------------------------------------------------------------------------
  def __init__(self):
    self._message_count=0
    self._bar_step=0
    self._last_text=""
    self._last_volatile=False
    self._silent_mode=False
    self._volatile_enabled=True
    self._progbar_enabled=True

  # ----------------------------------------------------------------------------------------------------------------------
  # Compute the available console width in characters.
  # Returns:
  #  int: Usable width for output; defaults to 9999 when stdout is not a TTY.
  # ----------------------------------------------------------------------------------------------------------------------
  def GetConsoleWidth(self):
    if sys.stdout.isatty():
      Console=os.get_terminal_size()
      ConsoleWidth=Console.columns
    else:
      ConsoleWidth=9999
    return ConsoleWidth

  # ----------------------------------------------------------------------------------------------------------------------
  # Compute the available console height in rows.
  # Returns:
  #   int: Usable height for output; defaults to 9999 when stdout is not a TTY.
  # ----------------------------------------------------------------------------------------------------------------------
  def GetConsoleHeight(self):
    if sys.stdout.isatty():
      Console=os.get_terminal_size()
      ConsoleHeight=Console.lines
    else:
      ConsoleHeight=9999
    return ConsoleHeight

  # ----------------------------------------------------------------------------------------------------------------------
  # Wrap a string with ANSI escape codes for foreground/background colors.
  # Args:
  #   Text (str): Text to decorate.
  #   FgColor (int): ANSI foreground color code.
  #   BkColor (int | None): Optional ANSI background color code; defaults to black.
  # Returns:
  #   str: Text wrapped in ANSI escape codes that reset at the end of the string.
  # ----------------------------------------------------------------------------------------------------------------------
  def AnsiColor(self,Text,FgColor,BkColor=None):
    BackgroundColor=";"+str(BkColor) if BkColor is not None else ""
    return f"{self.ANSI_ESCAPE_PREFIX}{FgColor}{BackgroundColor}m{Text}{self.ANSI_ESCAPE_PREFIX}0m"

  # ----------------------------------------------------------------------------------------------------------------------
  # Enable or disable silent mode for all printing operations.
  # Args:
  #   Enabled (bool): When True,suppresses all subsequent output until disabled.
  # ----------------------------------------------------------------------------------------------------------------------
  def SetSilentMode(self,Enabled):
    self._silent_mode=Enabled

  # ----------------------------------------------------------------------------------------------------------------------
  # Enable or disable volatile message output
  # Args:
  #   Enabled (bool): When True,all volatile message output is ignored
  # ----------------------------------------------------------------------------------------------------------------------
  def SetVolatileEnabled(self,Enabled):
    self._volatile_enabled=Enabled

  # ----------------------------------------------------------------------------------------------------------------------
  # Enable or disable progress bar on message output
  # Args:
  #   Enabled (bool): When True,progress bar output in messages is ignored
  # ----------------------------------------------------------------------------------------------------------------------
  def SetProgbarEnabled(self,Enabled):
    self._progbar_enabled=Enabled

  # ----------------------------------------------------------------------------------------------------------------------
  # Modified length function that takes into account ANSI OSC8 hyperlinks and ANSI color codes that do not count for printed length on the screen
  # Args:
  #   Value (str): String to measure.
  # Returns:
  #   int: Visible length of the string when printed to the console.
  # ----------------------------------------------------------------------------------------------------------------------
  def VisibleLength(self,Value):
    AnsiOsc8=re.compile(r"\x1b\]8;;.*?\x1b\\(.*?)\x1b\]8;;\x1b\\",re.VERBOSE)
    AnsiEscape=re.compile(r"""\x1B\[[0-9;]*[mK]""",re.VERBOSE)
    Clean=AnsiOsc8.sub(r"\1",Value)
    Clean=AnsiEscape.sub("",Clean)
    return len(Clean)

  # ----------------------------------------------------------------------------------------------------------------------
  # Wrap text to a given width while preserving indentation. Two characters are treated specially:
  # -\u00A0: Represents a non-breaking space that prevents wrapping at that position.
  # -\uE000: Represents a forced line break that splits the text into separate paragraphs.
  # Args:
  #   Text (str): Text to wrap.
  #   Width (int): Maximum line width before wrapping.
  #   Indentation (int): Spaces to prepend when continuing onto a new wrapped line.
  # Returns:
  #   str: Wrapped paragraph containing newline-delimited lines.
  # ----------------------------------------------------------------------------------------------------------------------
  def FormatParagraph(self,Text,Width,Indentation=0):

    #Split first by forced breaks
    Paragraphs=Text.split("\uE000")
    
    #Process each paragraph
    OutputLines=[]
    for Paragraph in Paragraphs:

      #Get words from text
      WorkingText=Paragraph.replace("\n"," ").replace("\r","").replace("\t"," ")
      while "  " in WorkingText:
        WorkingText=WorkingText.replace("  "," ")
      Words=WorkingText.split(" ")

      #Print words with wrapping
      Line=""
      for Word in Words:
        if self.VisibleLength(Line+Word) <= Width:
          Line+=Word+" "
        else:
          OutputLines.append(Line[:-1])
          Line=" "*Indentation+Word+" "
      if Line:
        OutputLines.append(Line[:-1])
    
    #Replace non-breaking spaces
    OutputLines=[Line.replace("\u00A0"," ") for Line in OutputLines]

    #Return formatted paragraph
    return "\n".join(OutputLines).strip("\n")

  # ----------------------------------------------------------------------------------------------------------------------
  # Output a formatted line with optional wheel,severity class,or progress bar.
  # Args:
  #   Text (str): Message body to print.
  #   Wheel (bool): When True,prefixes a spinner animation.
  #   Volatile (bool): When True,prints without newline so future output can overwrite it.
  #   Partial (bool): Behaves like volatile but meant for intermediate progress text.
  #   ClassName (str): Optional label prepended in square brackets (ERR/WARN/etc.).
  #   BarProgress (int | None): Explicit tick count to render inside the progress bar.
  #   BarLength (int | None): Total number of ticks that make up the progress bar.
  # Returns:
  #   None
  # ----------------------------------------------------------------------------------------------------------------------
  def Print(self,Text,Wheel=False,Volatile=False,Partial=False,ClassName="",BarProgress=None,BarLength=None):

    #Do not print if silent mode is enabled
    if self._silent_mode:
      return

    #Initializations
    ConsoleWidth=self.GetConsoleWidth()
    OutputText=Text
    Stream=sys.stdout

    #Switch to stderr for errors
    if ClassName.upper() in ["ERR","ERROR","FAIL","FAILURE"]:
      Stream=sys.stderr

    #Print wheel
    if Wheel==True:
      OutputText="["+self._WHEEL_CHARS[self._message_count % 4]+"] "+OutputText
      self._message_count+=1

    #Print progress bar
    if BarLength is not None and self._progbar_enabled==True:
      if BarProgress is not None:
        OutputText="["+"#"*BarProgress+"."*(BarLength-BarProgress)+"] "+OutputText
      else:
        if self._bar_step<BarLength:
          self._bar_step+=1
        OutputText="["+"#"*self._bar_step+"."*(BarLength-self._bar_step)+"] "+OutputText

    #Print class name
    if len(ClassName)!=0:
      OutputText="["+ClassName.upper()+"] "+OutputText

    #Clean last output of last message was volatile
    if self._last_volatile==True:
      print("\r",end="",flush=True,file=Stream)
      print(" "*len(self._last_text),end="\r",flush=True,file=Stream)

    #Output text
    if (Volatile==True and self._volatile_enabled==True) or Partial==True:
      OutputText=OutputText[:ConsoleWidth-2]
      print(OutputText,end="",flush=True,file=Stream)
    else:
      print(OutputText,file=Stream)

    #Save last message output
    self._last_text=OutputText
    self._last_volatile=(True if (Volatile==True and self._volatile_enabled==True) else False)

  # ----------------------------------------------------------------------------------------------------------------------
  # Adds a horizontal separation line to the row data list to use with PrintTable()
  # Args:
  #   Rows (list[list[str]]): Data rows
  # Returns:
  #   None
  # ----------------------------------------------------------------------------------------------------------------------
  def AddHline(self,Rows):
    Rows.append([self._SEPARATOR_ID])

  # ----------------------------------------------------------------------------------------------------------------------
  # Pretty-print a table with wrapping,alignment,and optional return buffer.
  # Args:
  #   Heading1 (list[str]): Primary header row labels.
  #   Heading2 (list[str] | None): Secondary header row labels or None when unused.
  #   ColAttributes (list[str]): Column format codes (alignment,wrapping,auto width,etc.).
  #   Rows (list[list[str]]): Data rows; use self._SEPARATOR_ID to insert horizontal dividers.
  #   ReturnOutput (bool): When True,returns a list of rendered lines instead of printing.
  #   ConsoleWidth (int | None): Optional console width override; defaults to detected width.
  # Returns:
  #   list[str] | None: Rendered table lines if ReturnOutput is True; otherwise None.
  # ----------------------------------------------------------------------------------------------------------------------
  def PrintTable(self,Heading1,Heading2,ColAttributes,Rows,ReturnOutput=False,ConsoleWidth=None):

    #Calculate max column to print according to data length and maximun width
    def CalculateTableWidth(Lengths,MaxWidth):
      Index=0
      TableWidth=1
      MaxColumn=0
      Truncated=False
      for CurrentLength in Lengths:
        TableWidth+=CurrentLength+1
        MaxColumn=Index
        if TableWidth>MaxWidth:
          Truncated=True
          MaxColumn-=1
          TableWidth-=CurrentLength+1
          break
        Index+=1
      return TableWidth,MaxColumn,Truncated

    #Exit if nothing to print
    if len(Rows)==0:
      if ReturnOutput==False:
        return
      else:
        return []
    #Init output
    Output=[]

    #Get console width
    if ConsoleWidth is not None:
      MaxWidth=ConsoleWidth
    else:
      MaxWidth=self.GetConsoleWidth()-1

    #Convert all row data to string and remove line breaks
    Rows=[[str(Field).replace("\n"," ") for Field in Row] for Row in Rows]

    #Calculate data column widths
    Lengths=[0]*len(Rows[0])
    for Row in Rows:
      Index=0
      for Field in Row:
        if Heading2 is not None:
          Lengths[Index]=max([Lengths[Index],self.VisibleLength(Field),self.VisibleLength(Heading1[Index]),self.VisibleLength(Heading2[Index])])
        else:
          Lengths[Index]=max([Lengths[Index],self.VisibleLength(Field),self.VisibleLength(Heading1[Index])])
        Index+=1

    #Calculate max column to print according to data length and maximun width
    TableWidth,MaxColumn,Truncated=CalculateTableWidth(Lengths,MaxWidth)

    #Adjust lengths if table is truncated and has resizeable columns
    ResizeableColumns=["W","M"]
    if Truncated and any(Attr for Attr in "".join(ColAttributes) if Attr in ResizeableColumns):
      while True:
        Resized=False
        Index=0
        for ColumnHeader in Heading1:
          if Lengths[Index]>self.VisibleLength(ColumnHeader) and any(Attr for Attr in ColAttributes[Index] if Attr in ResizeableColumns):
            Lengths[Index]-=1
            Resized=True
          Index+=1
        if Heading2 is not None:
          Index=0
          for ColumnHeader in Heading2:
            if Lengths[Index]>self.VisibleLength(ColumnHeader) and any(Attr for Attr in ColAttributes[Index] if Attr in ResizeableColumns):
              Lengths[Index]-=1
              Resized=True
            Index+=1
        if not Resized:
          break
        TableWidth,MaxColumn,Truncated=CalculateTableWidth(Lengths,MaxWidth)
        if not Truncated:
          break

    #Calculate separators
    RawSeparator="┼"
    Index=0
    for Column in Heading1:
      RawSeparator+="─"*Lengths[Index]+"┼"
      if Index >= MaxColumn:
        break
      Index+=1
    TopSeparator=("╭"+RawSeparator[1:-1]+"╮").replace("┼","┬")
    MidSeparator="├"+RawSeparator[1:-1]+"┤"
    BottomSeparator=("╰"+RawSeparator[1:-1]+"╯").replace("┼","┴")

    #Print column headings
    Output.append(TopSeparator)
    Line="│"
    Index=0
    for Column in Heading1:
      Line+=self.AnsiColor(Column.center(Lengths[Index]),self.ANSI_FB_CYAN,self.ANSI_BD_BLUE)+"│"
      if Index >= MaxColumn:
        break
      Index+=1
    Output.append(Line)
    if Heading2 is not None:
      Line="│"
      Index=0
      for Column in Heading2:
        Line+=self.AnsiColor(Column.center(Lengths[Index]),self.ANSI_FB_CYAN,self.ANSI_BD_BLUE)+"│"
        if Index >= MaxColumn:
          break
        Index+=1
      Output.append(Line)
    Output.append(MidSeparator)

    #Format data for multiline columns
    LeveledRows=[]
    for Row in Rows:
      if Row[0]==self._SEPARATOR_ID:
        LeveledRows.append(Row)
      else:
        Index=0
        MultiRow=[]
        for Field in Row:
          if "M" in ColAttributes[Index]:
            Values=self.FormatParagraph(Field,Lengths[Index]).split("\n")
          elif "S" in ColAttributes[Index]:
            Values=Field.split("\\n")
          else:
            Values=[Field]
          MultiRow.append(Values)
          Index+=1
        MaxValues=max([len(Values) for Values in MultiRow])
        for MultiIndex in range(0,MaxValues):
          LeveledRow=[]
          for Field in MultiRow:
            if MultiIndex <= len(Field)-1:
              LeveledRow.append(Field[MultiIndex])
            else:
              LeveledRow.append("")
          LeveledRows.append(LeveledRow)

    #Print table
    for Row in LeveledRows:
      if Row[0]==self._SEPARATOR_ID:
        Output.append(MidSeparator)
      else:
        Index=0
        Line="│"
        for Field in Row:
          if "A" not in ColAttributes[Index]:
            FieldValue=Field[:Lengths[Index]]
            if "L" in ColAttributes[Index]:
              FieldValue=FieldValue.ljust(Lengths[Index])
            elif "R" in ColAttributes[Index]:
              FieldValue=FieldValue.rjust(Lengths[Index])
            elif "C" in ColAttributes[Index]:
              FieldValue=FieldValue.center(Lengths[Index])
            else:
              FieldValue=FieldValue.ljust(Lengths[Index])
          else:
            Padding=Lengths[Index]-self.VisibleLength(Field)
            Padding=Padding if Padding>0 else 0
            if "L" in ColAttributes[Index]:
              FieldValue=Field+(" "*Padding)
            else:
              FieldValue=(" "*Padding)+Field
          Line+=FieldValue+"│"
          if Index >= MaxColumn:
            break
          Index+=1
        if self.VisibleLength(Line.replace(" ","").replace("│",""))!=0:
          Output.append(Line)
    Output.append(BottomSeparator)

    #Column count warning
    if MaxColumn<len(Lengths)-1:
      WarnMessage=f"Displaying {str(MaxColumn+1)} columns out of {str(len(Lengths))} columns due to console width ({MaxWidth} columns)"
    else:
      WarnMessage=""
    if self.VisibleLength(WarnMessage)!=0:
      Output.append(WarnMessage)

    #Print or return output
    if ReturnOutput:
      return Output
    else:
      for Line in Output:
        print(Line)
      return
