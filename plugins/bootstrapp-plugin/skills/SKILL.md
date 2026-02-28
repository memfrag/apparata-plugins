---
name: bootstrapp
description: Instantiate a project from a Bootstrapp template bundle
user-invocable: true
allowed-tools: Bash, Read
argument-hint: [template-path]
---

# Bootstrapp Template Instantiation

The user wants to instantiate a template. The template path is: $ARGUMENTS

## Instructions

### Step 1: Read the template spec

Read `Bootstrapp.json` inside the template path. Also read `Bootstrapp.md` if it exists and show its contents to the user.

### Step 2: Resolve parameters using defaults

Read the `parameters` array from the spec. For each parameter, use its `default` value. Skip parameters whose `dependsOn` references a parameter that evaluates to false.

If ANY parameter does NOT have a default value, ABORT. Do not run the script. Instead, list ALL parameters in a table showing:
- Parameter ID
- Type (String, Bool, Option)
- Default value or **MISSING**

Tell the user which parameters are missing defaults and ask them to provide values.

### Step 3: Run the script

Only run this if ALL parameters have values (from defaults or user-provided).

The script is at `scripts/bootstrapp.py` relative to this skill's directory.

```bash
python3 scripts/bootstrapp.py "<template-path>" \
  --param KEY1=VALUE1 --param KEY2=VALUE2 \
  --exclude-package NAME \
  --verbose
```

- Include ALL resolved parameters.
- Quote values with spaces: `--param "COPYRIGHT_HOLDER=Apparata AB"`
- For Option params, pass the option string: `--param LICENSE_TYPE=MIT`
- For Bool params, pass `true` or `false`: `--param GIT_INIT=false`
- Include all packages by default (no `--exclude-package` unless the user says otherwise).

### Step 4: Report result

The script prints the output path as its last line to stdout. Tell the user the full path. For Xcode projects, mention they can open the `.xcodeproj`.

Then ask if they want to open the output directory in Finder (`open "<path>"`).
