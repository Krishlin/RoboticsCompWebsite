# STEMsters Robotics Competition (SRC) Tournament Software

This runs the SRC tournament: registration, check-in, scheduling, referee
result entry, standings, bracket, and CSV export.

Right now this is a **shell** — every page loads and shows realistic fake
data, but nothing saves. Each person fills in their own folder behind
pages that already exist. See `CLAUDE.md` for the full project context,
who owns what, and the git workflow.

This guide assumes you have never run a Python project before. Follow the
commands for your operating system exactly.

## 1. Get the code

If you haven't already, clone the repository and open a terminal in the
project folder (the one with this README in it).

## 2. Create a virtual environment

A virtual environment keeps this project's Python packages separate from
everything else on your computer.

**Mac / Linux:**
```
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**
```
python -m venv venv
venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```
python -m venv venv
venv\Scripts\activate.bat
```

You'll know it worked because your terminal prompt now starts with
`(venv)`. You need to run the activate command every time you open a new
terminal to work on this project.

## 3. Install dependencies

Same command on every OS, once the virtual environment is active:

```
pip install -r requirements.txt
```

## 4. Set up your .env file

The app reads some secret values (like Supabase credentials) from a file
called `.env` in the project root, which is never committed to git.

Copy the example file and fill in the real values (ask Krish for them):

**Mac / Linux:**
```
cp .env.example .env
```

**Windows:**
```
copy .env.example .env
```

Then open `.env` in a text editor and paste in the real values.

## 5. Run the app

```
python run.py
```

You should see something like:

```
* Running on http://127.0.0.1:5000
```

Open that address in your browser. You should land on the home page,
which lists every page in the app and who's building it.

## 6. Stop the app

Press `Ctrl+C` in the terminal.

## Making changes

1. Make sure your virtual environment is active (step 2).
2. Edit files inside your own blueprint folder only — see `CLAUDE.md` for
   the ownership rules and git workflow.
3. Save the file, then refresh your browser. Flask's debug mode (already
   on in `run.py`) reloads the app automatically — you don't need to
   restart it.

## Troubleshooting

- **`python` or `pip` not found** — try `python3` / `pip3` instead (common
  on Mac).
- **`ModuleNotFoundError: No module named 'flask'`** — your virtual
  environment probably isn't active. Re-run the activate command from
  step 2.
- **Port already in use** — another program (maybe an old `run.py` you
  forgot to stop) is using port 5000. Stop it, or ask for help.
