# mppt
### project_summary

This program works with a Squidstat Prime potentiostat to run
maximum power point tracking for the purpose of accelerated
lifetime testing.

The code currently handles up to 4 channels for the one potentiostat
and runs ADD

### installation_procedure
Download an IDE such as VSCode: https://code.visualstudio.com/
VSCode is what I use, so instructions will be based on it.
On the left most tab, click on "Extensions" and make sure the
following are installed:
  Pylance
  Python
  Python Environments
  GitHub Pull Requests
  Even Better TOML
  Rainbow CSV is helpful
  Error Lens is also helpful
If they're not installed, they can easily be searched in the 
Search Extensions field.

Download Git: https://git-scm.com/

The Squidstat Prime potentiostat requires an older version of Python. 
I have used Python 3.10.11: https://www.python.org/downloads/release/python-31011/

Open a folder in VSCode where you will want to place the MPPT repository

Run the command: git clone https://github.com/JasonSchultzz/mppt
Open the MPPT folder in VSCode to make sure the environment is set to this folder

Press Ctrl + Shift + P to pull down the Python options at the top of VSCode and 
select Python: Create Environment.

Select the "venv" option to create a virtual environment separate from other
Python environments since the version we will use will be older.

Make sure Python 3.10.11 is the version selected.

In the command line in VSCode, run: "pip install ."
This will install almost all dependencies for the code to run.

Now install the Squidstat dependencies with the provided file in the repo.
Run the command: pip install .\SquidstatPyLibrary-1.10.3.0-py3-none-win_amd64.whl

Everything should now be setup. Next the input.toml file is filled out to desired
specifications, then the program is ran through "main.py"

### code_demonstration

```
import sys
from PySide6.QtWidgets import QApplication
from mppt.mppt import InputData

CONFIG = "./config/input.toml"

def main():
    app = QApplication()
    input_data = InputData(CONFIG)
    manager = SquidstatMppt(input_data)
    manager.start_JV_scans()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```
