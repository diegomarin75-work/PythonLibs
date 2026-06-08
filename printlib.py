#Import libraries
import os
import re
import sys

# -------------------------------------------------------------------------------------------------------------------
# PrintingLibrary provides console formatting, ANSI color support, and table-printing capabilities.
# -------------------------------------------------------------------------------------------------------------------
class PrintingLibrary:

  #Private constants used for separator identification and spinner animation characters
  _SEPARATOR_ID = "$SEP$"
  _WHEEL_CHARS = ["-", "\\", "|", "/"]

  #fmt: off
  #ANSI color escape constants
  ANSI_ESCAPE_PREFIX="\033["
  ANSI_FD_BLACK  =30; ANSI_BD_BLACK  =40; ANSI_FB_BLACK  =90; ANSI_BB_BLACK  =100;
  ANSI_FD_RED    =31; ANSI_BD_RED    =41; ANSI_FB_RED    =91; ANSI_BB_RED    =101;
  ANSI_FD_GREEN  =32; ANSI_BD_GREEN  =42; ANSI_FB_GREEN  =92; ANSI_BB_GREEN  =102;
  ANSI_FD_YELLOW =33; ANSI_BD_YELLOW =43; ANSI_FB_YELLOW =93; ANSI_BB_YELLOW =103;
  ANSI_FD_BLUE   =34; ANSI_BD_BLUE   =44; ANSI_FB_BLUE   =94; ANSI_BB_BLUE   =104;
  ANSI_FD_MAGENTA=35; ANSI_BD_MAGENTA=45; ANSI_FB_MAGENTA=95; ANSI_BB_MAGENTA=105;
  ANSI_FD_CYAN   =36; ANSI_BD_CYAN   =46; ANSI_FB_CYAN   =96; ANSI_BB_CYAN   =106;
  ANSI_FD_WHITE  =37; ANSI_BD_WHITE  =47; ANSI_FB_WHITE  =97; ANSI_BB_WHITE  =107;
  #fmt: on

  # -----------------------------------------------------------------------------------------------------------------
  # This method initializes the PrintingLibrary instance and sets all default state values.
  # Args:
  #   None
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def __init__(self):

    #Initialize all instance state variables to their default values
    self._MessageCount = 0
    self._BarStep = 0
    self._LastText = ""
    self._LastVolatile = False
    self._SilentMode = False
    self._ColorEnabled = True
    self._VolatileEnabled = True
    self._ProgbarEnabled = True

  # -----------------------------------------------------------------------------------------------------------------
  # This method returns the available console width in characters.
  # Args:
  #   None
  # Returns:
  #   int: Usable column count; defaults to 9999 when stdout is not a TTY.
  # -----------------------------------------------------------------------------------------------------------------
  def GetConsoleWidth(self):

    #Query terminal size when running in an interactive TTY
    if sys.stdout.isatty():
      Console = os.get_terminal_size()
      ConsoleWidth = Console.columns
    else:
      ConsoleWidth = 9999
    return ConsoleWidth

  # -----------------------------------------------------------------------------------------------------------------
  # This method returns the available console height in rows.
  # Args:
  #   None
  # Returns:
  #   int: Usable row count; defaults to 9999 when stdout is not a TTY.
  # -----------------------------------------------------------------------------------------------------------------
  def GetConsoleHeight(self):

    #Query terminal size when running in an interactive TTY
    if sys.stdout.isatty():
      Console = os.get_terminal_size()
      ConsoleHeight = Console.lines
    else:
      ConsoleHeight = 9999
    return ConsoleHeight

  # -----------------------------------------------------------------------------------------------------------------
  # This method wraps a string with ANSI escape codes for foreground and optional background colors.
  # Args:
  #   Text (str): Text to decorate.
  #   FgColor (int): ANSI foreground color code.
  #   BkColor (int | None): Optional ANSI background color code; omitted when None.
  # Returns:
  #   str: Text wrapped in ANSI escape codes that reset at the end of the string.
  # -----------------------------------------------------------------------------------------------------------------
  def AnsiColor(self, Text, FgColor, BkColor=None):

    #Return plain text when color output is disabled
    if self._ColorEnabled == False:
      return Text

    #Wrap text with ANSI color escape codes
    BackgroundColor = ";" + str(BkColor) if BkColor is not None else ""
    return f"{self.ANSI_ESCAPE_PREFIX}{FgColor}{BackgroundColor}m{Text}{self.ANSI_ESCAPE_PREFIX}0m"

  # -----------------------------------------------------------------------------------------------------------------
  # This method sets whether ANSI color codes should be included in output.
  # Args:
  #   Enabled (bool): When True, ANSI color codes are emitted; when False, output is plain text.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def SetColorEnabled(self, Enabled):

    #Update color-enabled flag
    self._ColorEnabled = Enabled

  # -----------------------------------------------------------------------------------------------------------------
  # This method enables or disables silent mode, suppressing all output when active.
  # Args:
  #   Enabled (bool): When True, all subsequent output is suppressed.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def SetSilentMode(self, Enabled):

    #Update silent-mode flag
    self._SilentMode = Enabled

  # -----------------------------------------------------------------------------------------------------------------
  # This method enables or disables volatile message output.
  # Args:
  #   Enabled (bool): When True, volatile messages are emitted; when False, they are discarded.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def SetVolatileEnabled(self, Enabled):

    #Update volatile-enabled flag
    self._VolatileEnabled = Enabled

  # -----------------------------------------------------------------------------------------------------------------
  # This method enables or disables the progress bar in message output.
  # Args:
  #   Enabled (bool): When True, progress bar output is rendered; when False, it is suppressed.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def SetProgbarEnabled(self, Enabled):

    #Update progress-bar-enabled flag
    self._ProgbarEnabled = Enabled

  # -----------------------------------------------------------------------------------------------------------------
  # This method returns the visible printed length of a string, ignoring ANSI escape sequences.
  # Args:
  #   Value (str): String to measure.
  # Returns:
  #   int: Visible length of the string when printed to the console.
  # -----------------------------------------------------------------------------------------------------------------
  def VisibleLength(self, Value):

    #Strip ANSI OSC8 hyperlink sequences and color codes before measuring
    ANSI_OSC8 = re.compile(r"\x1b\]8;;.*?\x1b\\(.*?)\x1b\]8;;\x1b\\", re.VERBOSE)
    ANSI_ESCAPE = re.compile(r"""\x1B\[[0-9;]*[mK]""", re.VERBOSE)
    Clean = ANSI_OSC8.sub(r"\1", Value)
    Clean = ANSI_ESCAPE.sub("", Clean)
    return len(Clean)

  # -----------------------------------------------------------------------------------------------------------------
  # This method wraps text to a given width while preserving indentation.
  # Special characters: \u00A0 is a non-breaking space; \uE000 is a forced line break.
  # Args:
  #   Text (str): Text to wrap.
  #   Width (int): Maximum line width before wrapping.
  #   Indentation (int): Number of spaces to prepend when continuing onto a new wrapped line.
  # Returns:
  #   str: Wrapped text containing newline-delimited lines.
  # -----------------------------------------------------------------------------------------------------------------
  def FormatParagraph(self, Text, Width, Indentation=0):

    #Split input text into paragraphs at forced line-break characters
    Paragraphs = Text.split("\uE000")

    #Process each paragraph independently
    OutputLines = []
    for Paragraph in Paragraphs:

      #Normalize whitespace and split into words
      WorkingText = Paragraph.replace("\n", " ").replace("\r", "").replace("\t", " ")
      while "  " in WorkingText:
        WorkingText = WorkingText.replace("  ", " ")
      Words = WorkingText.split(" ")

      #Wrap words into lines within the specified width
      Line = ""
      for Word in Words:
        if self.VisibleLength(Line + Word) <= Width:
          Line += Word + " "
        else:
          OutputLines.append(Line[:-1])
          Line = " " * Indentation + Word + " "
      if Line:
        OutputLines.append(Line[:-1])

    #Replace non-breaking space placeholders with regular spaces
    OutputLines = [Line.replace("\u00A0", " ") for Line in OutputLines]

    #Return all lines joined by newlines
    return "\n".join(OutputLines).strip("\n")

  # -----------------------------------------------------------------------------------------------------------------
  # This method outputs a formatted message with optional spinner, severity class, or progress bar.
  # Args:
  #   Text (str): Message body to print.
  #   Wheel (bool): When True, prefixes a spinner animation character.
  #   Volatile (bool): When True, prints without newline so future output can overwrite it.
  #   Partial (bool): Like Volatile but intended for intermediate progress text.
  #   ClassName (str): Optional label prepended in square brackets (e.g. ERR, WARN).
  #   BarProgress (int | None): Explicit tick count to render inside the progress bar.
  #   BarLength (int | None): Total number of ticks that make up the progress bar.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def Print(self, Text, Wheel=False, Volatile=False, Partial=False, ClassName="", BarProgress=None, BarLength=None):

    #Do not print if silent mode is enabled
    if self._SilentMode:
      return

    #Initialize output variables
    ConsoleWidth = self.GetConsoleWidth()
    OutputText = Text
    Stream = sys.stdout

    #Switch to stderr stream for error-class messages
    if ClassName.upper() in ["ERR", "ERROR", "FAIL", "FAILURE"]:
      Stream = sys.stderr

    #Prepend spinner character when wheel mode is requested
    if Wheel == True:
      OutputText = "[" + self._WHEEL_CHARS[self._MessageCount % 4] + "] " + OutputText
      self._MessageCount += 1

    #Render progress bar when bar length is provided
    if BarLength is not None and self._ProgbarEnabled == True:
      if BarProgress is not None:
        OutputText = self.AnsiColor("█"*BarProgress,self.ANSI_FD_WHITE) + self.AnsiColor("█"*(BarLength-BarProgress),self.ANSI_FB_BLACK) + " " + OutputText
      else:
        if self._BarStep < BarLength:
          self._BarStep += 1
        OutputText = self.AnsiColor("█"*self._BarStep,self.ANSI_FD_WHITE) + self.AnsiColor("█"*(BarLength-self._BarStep),self.ANSI_FB_BLACK) + " " + OutputText

    #Prepend class name label when provided
    if len(ClassName) != 0:
      OutputText = "[" + ClassName.upper() + "] " + OutputText

    #Erase previous line when the last message was volatile
    if self._LastVolatile == True:
      print("\r", end="", flush=True, file=Stream)
      print(" " * len(self._LastText), end="\r", flush=True, file=Stream)

    #Print text in volatile or normal mode
    if (Volatile == True and self._VolatileEnabled == True) or Partial == True:
      if self.VisibleLength(OutputText) > ConsoleWidth - 2:
        OutputText = OutputText[:ConsoleWidth - 2]
      print(OutputText, end="", flush=True, file=Stream)
    else:
      print(OutputText, file=Stream)

    #Save last message output state for next call
    self._LastText = OutputText
    self._LastVolatile = (True if (Volatile == True and self._VolatileEnabled == True) else False)

  # -----------------------------------------------------------------------------------------------------------------
  # This method appends a horizontal separator marker to the row data list for use with PrintTable.
  # Args:
  #   Rows (list): Data rows list to append the separator to.
  # Returns:
  #   None
  # -----------------------------------------------------------------------------------------------------------------
  def AddHline(self, Rows):

    #Append a separator marker row to the list
    Rows.append([self._SEPARATOR_ID])

  # -----------------------------------------------------------------------------------------------------------------
  # This method pretty-prints a table with column wrapping, alignment, and optional return buffer.
  # Args:
  #   Heading1 (list): Primary header row labels.
  #   Heading2 (list | None): Secondary header row labels, or None when unused.
  #   ColAttributes (list): Column format codes (alignment, wrapping, auto-width, etc.).
  #   Rows (list): Data rows; use AddHline to insert horizontal dividers.
  #   ReturnOutput (bool): When True, returns rendered lines instead of printing them.
  #   ConsoleWidth (int | None): Optional console width override; defaults to detected width.
  # Returns:
  #   list | None: Rendered table lines when ReturnOutput is True; otherwise None.
  # -----------------------------------------------------------------------------------------------------------------
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
