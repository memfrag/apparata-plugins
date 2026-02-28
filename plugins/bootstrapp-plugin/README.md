# Bootstrapp User Manual

A Claude Code skill for instantiating projects from template bundles. Define a template once, then generate fully configured projects with parameter substitution, conditional file inclusion, and optional Xcode project generation.

---

## Table of Contents

1. [Invoking the Skill](#1-invoking-the-skill)
2. [Template Bundle Structure](#2-template-bundle-structure)
3. [The Specification File (Bootstrapp.json)](#3-the-specification-file-bootstrappjson)
4. [Template Syntax](#4-template-syntax)
5. [Parameters](#5-parameters)
6. [Conditional Inclusion](#6-conditional-inclusion)
7. [Packages](#7-packages)
8. [Xcode Project Generation](#8-xcode-project-generation)
9. [Worked Example: Creating a Template from Scratch](#9-worked-example-creating-a-template-from-scratch)
10. [Advanced Usage](#10-advanced-usage)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Invoking the Skill

### Basic Usage

In Claude Code, type:

```
/bootstrapp /path/to/My Template
```

Claude will:
1. Read the template specification
2. Ask you to confirm or change each parameter value interactively
3. Ask about package selection (if applicable)
4. Run the template engine
5. Report the output path

### Pre-specifying Parameters

You can skip the interactive prompts for some or all parameters by passing them directly:

```
/bootstrapp /path/to/My Template --param APP_NAME=MyApp --param GIT_INIT=false
```

Parameters provided via `--param` will not be asked about. Any remaining parameters will still be prompted interactively.

### Output Location

Generated projects are placed at:

```
/tmp/Results/YYYY-MM-DD/<output-directory-name>/
```

The output directory name is itself a template expression (defined by `outputDirectoryName` in the spec). For example, if `outputDirectoryName` is `<{APP_NAME}>` and you set `APP_NAME=MyApp`, the output will be at `/tmp/Results/2026-02-28/MyApp/`.

For Xcode Project templates, the final reported path will be the `.xcodeproj` file inside that directory.

---

## 2. Template Bundle Structure

A template bundle is a directory with this layout:

```
My Template/
├── Bootstrapp.json          # Required: template specification
├── Bootstrapp.md            # Optional: description shown to the user
├── Content/                 # Required: the actual template files
│   ├── <{APP_NAME}>/        #   Directories can use template syntax in names
│   │   ├── main.swift       #   Files whose content gets rendered
│   │   └── icon.png         #   Binary files are copied as-is
│   ├── README.md
│   └── ...
└── Preview/                 # Optional: preview images (not used by the skill)
    └── 1.png
```

### The Content/ Directory

Everything inside `Content/` is what gets instantiated into the output. The directory structure is preserved, and both directory names and file names can contain template expressions.

For example, a directory named `<{APP_NAME}>` will be renamed to whatever the user provides for `APP_NAME`.

### Binary vs. Text Files

The spec's `parametrizableFiles` array lists regex patterns for files whose **content** should be processed through the template engine. Files not matching any pattern are copied verbatim (binary-safe). This means you can safely include images, fonts, archives, etc. in your template.

---

## 3. The Specification File (Bootstrapp.json)

This is the heart of your template. Here is a complete reference:

```json
{
    "specificationVersion": "1.0.0",
    "templateVersion": "1.0.0",
    "id": "My Template",
    "type": "General",
    "description": "A short description shown to the user.",
    "outputDirectoryName": "<{PROJECT_NAME}>",
    "substitutions": { ... },
    "parameters": [ ... ],
    "parametrizableFiles": [ ... ],
    "includeDirectories": [ ... ],
    "includeFiles": [ ... ],
    "packages": [ ... ]
}
```

### Fields Reference

| Field | Required | Description |
|---|---|---|
| `specificationVersion` | Yes | Always `"1.0.0"` |
| `templateVersion` | Yes | Your template's version (e.g. `"1.0.0"`) |
| `id` | Yes | Unique identifier for the template |
| `type` | Yes | One of: `"General"`, `"Swift Package"`, `"Xcode Project"` |
| `description` | Yes | Human-readable description |
| `projectSpecification` | Only for Xcode Project | Filename of the XcodeGen YAML spec (e.g. `"XcodeProject.yml"`) |
| `outputDirectoryName` | Yes | Template expression for the output directory name |
| `substitutions` | No | Static key-value pairs added to the context |
| `parameters` | No | Array of user-facing parameters (see [Parameters](#5-parameters)) |
| `parametrizableFiles` | No | Array of regex patterns for files to render |
| `includeDirectories` | No | Conditional directory inclusion rules |
| `includeFiles` | No | Conditional file inclusion rules |
| `packages` | No | Array of Swift package dependencies |

### Project Types

- **`"General"`** — Any project type. Files are rendered and output as-is.
- **`"Swift Package"`** — Same as General, but semantically indicates a Swift package.
- **`"Xcode Project"`** — After rendering files, runs `xcodegen` to generate an `.xcodeproj`. Requires `projectSpecification` to point to a XcodeGen YAML file in the Content/ directory.

### Substitutions

Static key-value pairs that are injected into the template context. Useful for values that shouldn't be user-facing parameters but are needed in templates:

```json
"substitutions": {
    "DOT": ".",
    "MARKETING_VERSION": "1.0.0",
    "CURRENT_PROJECT_VERSION": "1"
}
```

The `DOT` substitution is a common pattern — it lets you create files/directories with names starting with `.` (like `.gitignore`) without confusing file systems or version control:

```
Content/
└── <{DOT}>gitignore       →  .gitignore
```

### Built-in Context Variables

These are automatically available in all templates without needing to define them:

| Variable | Example Value |
|---|---|
| `CURRENT_YEAR` | `2026` |
| `CURRENT_DATE` | `2026-02-28` |
| `CURRENT_DATETIME` | `2026-02-28T14:30:00` |
| `CURRENT_TIME` | `14:30:00` |
| `TEMPLATE_VERSION` | `1.0.0` |

---

## 4. Template Syntax

The template engine uses `<{` and `}>` as delimiters (not Mustache's `{{ }}`).

### Variable Substitution

```
<{ VARIABLE_NAME }>
```

Inserts the value of `VARIABLE_NAME` from the context. If the variable is `nil` or not found, nothing is output.

Whitespace inside the delimiters is flexible:

```
<{APP_NAME}>            works
<{ APP_NAME }>          works
<{  APP_NAME  }>        works
```

### Dot-Path Access

Access nested values with dot notation:

```
<{ package.name }>
<{ package.url }>
```

This is primarily used inside `for` loops to access properties of loop items.

### Transformers

Apply transformations to values using `#` prefixes:

```
<{ #lowercased APP_NAME }>
<{ #uppercased APP_NAME }>
<{ #uppercasingFirstLetter APP_NAME }>
<{ #lowercasingFirstLetter APP_NAME }>
<{ #trimmed APP_NAME }>
<{ #removingWhitespace APP_NAME }>
```

Chain multiple transformers (applied left to right):

```
<{ #lowercased #trimmed APP_NAME }>
```

Available transformers:

| Transformer | Effect | Example |
|---|---|---|
| `#lowercased` | Lowercase entire string | `MyApp` -> `myapp` |
| `#uppercased` | Uppercase entire string | `MyApp` -> `MYAPP` |
| `#uppercasingFirstLetter` | Uppercase first character | `myApp` -> `MyApp` |
| `#lowercasingFirstLetter` | Lowercase first character | `MyApp` -> `myApp` |
| `#trimmed` | Strip leading/trailing whitespace | `" hello "` -> `"hello"` |
| `#removingWhitespace` | Remove all whitespace | `"my app"` -> `"myapp"` |

### Conditionals

```
<{ if BOOL_VAR }>
This is included when BOOL_VAR is true.
<{ end }>
```

With else:

```
<{ if HAS_FEATURE }>
Feature is enabled.
<{ else }>
Feature is disabled.
<{ end }>
```

### Comparison Operators

Compare a variable to a string literal:

```
<{ if LICENSE_TYPE == 'MIT' }>
MIT License content here.
<{ end }>

<{ if LICENSE_TYPE != 'None' }>
A license file exists.
<{ end }>
```

String literals can use single or double quotes.

### Boolean Logic

Combine conditions with `and`, `or`, `not`, and parentheses:

```
<{ if HAS_FEATURE and IS_ENABLED }>
Both conditions are true.
<{ end }>

<{ if A or B }>
At least one is true.
<{ end }>

<{ if not DISABLED }>
Not disabled.
<{ end }>

<{ if not (A and B) }>
At least one is false.
<{ end }>
```

### Truthiness Rules

When evaluating a variable as a boolean:
- `nil` / missing -> `false`
- `true` -> `true`
- `false` -> `false`
- Any other non-nil value -> `true`

### Loops

Iterate over a list:

```
<{ for package in packages }>
    <{ package.name }>: <{ package.url }> (<{ package.version }>)
<{ end }>
```

The loop variable (`package`) is scoped to the loop body and can be accessed with dot-path notation.

### Imports

Include and render another file:

```
<{ import "../../Common/Licenses/MIT.txt" }>
```

The imported file path is resolved relative to the `Content/` directory of the template bundle. The imported file is itself rendered through the template engine, so it can contain template expressions.

This is useful for sharing content across multiple templates (e.g., license files in a common directory alongside your template bundles).

### Newline Handling

The template engine automatically strips extra newlines around control-flow tags (`if`, `for`, `else`, `end`, `import`). This means you can write:

```
Line before
<{ if SHOW_MIDDLE }>
Middle line
<{ end }>
Line after
```

And when `SHOW_MIDDLE` is false, the output will be:

```
Line before
Line after
```

...without any blank lines where the `if`/`end` tags were. Variable tags (`<{ VAR }>`) do **not** trigger this newline stripping — they are inline substitutions.

---

## 5. Parameters

Parameters are the values the user is asked to provide when instantiating a template.

### String Parameters

A free-text value, optionally validated by a regex:

```json
{
    "name": "App Name",
    "id": "APP_NAME",
    "type": "String",
    "validationRegex": "^[A-Za-z0-9_\\- ]+$"
}
```

With a default value:

```json
{
    "name": "Copyright Holder",
    "id": "COPYRIGHT_HOLDER",
    "type": "String",
    "default": "Apparata AB"
}
```

- `name` — Human-readable label shown to the user.
- `id` — The key used in templates (e.g. `<{ APP_NAME }>`).
- `validationRegex` — Optional. Regex the value must match.
- `default` — Optional. Pre-filled value. If no default is provided, the parameter is required.

### Bool Parameters

A true/false toggle:

```json
{
    "name": "Init git repo",
    "id": "GIT_INIT",
    "type": "Bool",
    "default": true
}
```

Bool values can be used directly in conditions: `<{ if GIT_INIT }>`.

### Option Parameters

A selection from a fixed list of choices:

```json
{
    "name": "License",
    "id": "LICENSE_TYPE",
    "type": "Option",
    "default": 0,
    "options": [
        "None",
        "MIT",
        "BSD",
        "Apache 2"
    ]
}
```

- `options` — The list of available choices.
- `default` — Index (0-based) of the default selection.

The selected option's **string value** (e.g. `"MIT"`) is what gets injected into the context, not the index.

### Parameter Dependencies

A parameter can depend on another parameter. If the dependency evaluates to false, the dependent parameter is skipped during interactive collection:

```json
{
    "name": "Enable URL Scheme",
    "id": "ENABLE_URL_SCHEME",
    "type": "Bool",
    "default": false
},
{
    "name": "URL Scheme",
    "id": "CUSTOM_URL_SCHEME",
    "type": "String",
    "validationRegex": "^[a-zA-Z0-9_]+$",
    "dependsOn": "ENABLE_URL_SCHEME"
}
```

In this example, `CUSTOM_URL_SCHEME` is only asked about if `ENABLE_URL_SCHEME` is `true`.

---

## 6. Conditional Inclusion

### Conditional Directories

Include or exclude entire directory trees based on conditions:

```json
"includeDirectories": [
    {
        "if": "GIT_INIT",
        "directories": [
            "<{DOT}>git"
        ]
    }
]
```

When the condition evaluates to **false**, the listed directories (and all their contents) are excluded from the output. When the condition is **true**, they are included normally.

Directory paths are relative to `Content/` and can themselves contain template expressions.

### Conditional Files

Include or exclude individual files:

```json
"includeFiles": [
    {
        "if": "LICENSE_TYPE != 'None'",
        "files": [
            "LICENSE"
        ]
    },
    {
        "if": "ENABLE_URL_SCHEME",
        "files": [
            "Info.plist"
        ]
    }
]
```

The condition syntax is the same as in template tags — it supports boolean variables, comparisons with `==`/`!=`, and `and`/`or`/`not` logic.

### Placeholder Files

Git does not track empty directories. If your template needs an empty directory to exist, place a file named `.ignored-placeholder` inside it. These files are automatically excluded from the output.

---

## 7. Packages

The `packages` array defines Swift package dependencies. These are available in the template context as a list that can be iterated with `for` loops:

```json
"packages": [
    {
        "name": "MyLibrary",
        "url": "https://github.com/example/MyLibrary.git",
        "version": "1.0.0"
    }
]
```

Use in a template:

```yaml
packages:
<{ for package in packages }>
    <{ package.name }>:
        url: <{ package.url }>
        exactVersion: <{ package.version }>
<{ end }>
```

When invoking the skill, users can exclude specific packages:

```
/bootstrapp /path/to/template --param APP_NAME=MyApp
```

The skill will ask about package selection interactively, or you can exclude packages on the command line when calling the Python script directly:

```bash
python3 ~/.claude/skills/bootstrapp/scripts/bootstrapp.py /path/to/template \
    --param APP_NAME=MyApp \
    --exclude-package MyLibrary
```

---

## 8. Xcode Project Generation

For templates with `"type": "Xcode Project"`, the engine will run `xcodegen` after rendering all files to generate an `.xcodeproj`.

### Requirements

- [XcodeGen](https://github.com/yonaskolb/XcodeGen) must be installed and available in your `PATH`.
- The spec must include `"projectSpecification"` pointing to a XcodeGen YAML file within Content/:

```json
{
    "type": "Xcode Project",
    "projectSpecification": "XcodeProject.yml"
}
```

### What Happens

1. All template files are rendered normally (including the YAML spec itself).
2. `xcodegen generate --spec <rendered-spec.yml>` is run in the output directory.
3. An `IDETemplateMacros.plist` is written under `.xcodeproj/xcshareddata/` with a copyright header using `CURRENT_YEAR` and `COPYRIGHT_HOLDER`.

### Presets

If your template bundle contains a `Presets/` directory (for XcodeGen setting presets), the engine will set the working directory to that path before running `xcodegen`, so preset references in your YAML spec resolve correctly.

---

## 9. Worked Example: Creating a Template from Scratch

Let's create a simple Python project template.

### Step 1: Create the Directory Structure

```
Python CLI Template/
├── Bootstrapp.json
├── Bootstrapp.md
└── Content/
    ├── <{PROJECT_NAME}>/
    │   ├── __init__.py
    │   └── main.py
    ├── <{DOT}>gitignore
    ├── README.md
    ├── setup.py
    └── LICENSE
```

### Step 2: Write Bootstrapp.json

```json
{
    "specificationVersion": "1.0.0",
    "templateVersion": "1.0.0",
    "id": "Python CLI",
    "type": "General",
    "description": "A simple Python CLI project with optional license.",
    "outputDirectoryName": "<{PROJECT_NAME}>",
    "substitutions": {
        "DOT": "."
    },
    "parameters": [
        {
            "name": "Project Name",
            "id": "PROJECT_NAME",
            "type": "String",
            "validationRegex": "^[a-z][a-z0-9_]*$"
        },
        {
            "name": "Author",
            "id": "AUTHOR",
            "type": "String",
            "default": "Your Name"
        },
        {
            "name": "Description",
            "id": "PROJECT_DESCRIPTION",
            "type": "String",
            "default": "A Python CLI tool"
        },
        {
            "name": "License",
            "id": "LICENSE_TYPE",
            "type": "Option",
            "default": 1,
            "options": ["None", "MIT", "Apache 2"]
        },
        {
            "name": "Include Tests",
            "id": "INCLUDE_TESTS",
            "type": "Bool",
            "default": true
        }
    ],
    "parametrizableFiles": [
        ".*\\.py",
        ".*\\.md",
        ".*\\.txt",
        "LICENSE"
    ],
    "includeFiles": [
        {
            "if": "LICENSE_TYPE != 'None'",
            "files": ["LICENSE"]
        }
    ],
    "includeDirectories": [
        {
            "if": "INCLUDE_TESTS",
            "directories": ["tests"]
        }
    ]
}
```

### Step 3: Write Bootstrapp.md

```markdown
# Features

A minimal Python CLI project template.

- Configurable license (MIT, Apache 2, or none)
- Optional test directory with pytest
- Standard setup.py with metadata
```

### Step 4: Write Template Files

**Content/README.md:**

```markdown
# <{PROJECT_NAME}>

<{PROJECT_DESCRIPTION}>

## Installation

pip install -e .

## Usage

<{PROJECT_NAME}>

<{ if LICENSE_TYPE != 'None' }>

## License

See the LICENSE file.
<{ end }>
```

**Content/setup.py:**

```python
from setuptools import setup, find_packages

setup(
    name="<{PROJECT_NAME}>",
    version="0.1.0",
    author="<{AUTHOR}>",
    description="<{PROJECT_DESCRIPTION}>",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "<{PROJECT_NAME}>=<{PROJECT_NAME}>.main:main",
        ],
    },
    python_requires=">=3.8",
)
```

**Content/\<{PROJECT_NAME}\>/main.py:**

```python
# Copyright <{CURRENT_YEAR}> <{AUTHOR}>

def main():
    print("Hello from <{PROJECT_NAME}>!")

if __name__ == "__main__":
    main()
```

### Step 5: Invoke It

```
/bootstrapp /path/to/Python CLI Template
```

Or with pre-specified parameters:

```
/bootstrapp "/path/to/Python CLI Template" --param PROJECT_NAME=mytool --param AUTHOR="Jane Doe"
```

---

## 10. Advanced Usage

### Running the Python Script Directly

You can bypass the Claude skill and run the engine directly:

```bash
python3 ~/.claude/skills/bootstrapp/scripts/bootstrapp.py \
    "/path/to/template" \
    --param KEY1=VALUE1 \
    --param KEY2=VALUE2 \
    --exclude-package SomePackage \
    --output-dir /custom/output/path \
    --verbose
```

Options:
- `--param KEY=VALUE` — Set a parameter (repeatable). `true`/`false` strings are parsed as booleans.
- `--exclude-package NAME` — Remove a spec-defined package (repeatable).
- `--output-dir DIR` — Override the default output location.
- `--verbose` — Print progress messages to stderr.

The output path is printed as the last line to stdout.

### Sharing Content Across Templates

Use the `import` tag to include files from outside the template's Content/ directory. Paths resolve relative to Content/, so `../../` goes up to the parent of the template bundle:

```
Templates/
├── Common/
│   └── Licenses/
│       ├── MIT.txt
│       └── Apache 2.txt
├── iOS App Template/
│   ├── Bootstrapp.json
│   └── Content/
│       └── LICENSE          ← contains: <{ import "../../Common/Licenses/MIT.txt" }>
└── macOS App Template/
    ├── Bootstrapp.json
    └── Content/
        └── LICENSE          ← can import the same shared files
```

### Template Expressions in File and Directory Names

Both file and directory names within `Content/` are rendered through the template engine. This means you can use any template expression:

```
Content/
├── <{APP_NAME}>/               ← renamed to the app name
├── <{DOT}>gitignore            ← becomes .gitignore
└── <{#lowercased APP_NAME}>/   ← lowercased version
```

Keep in mind that only variable substitution and transformers make sense in names — you cannot use `if`/`for`/`import` in file or directory names.

---

## 11. Troubleshooting

### "xcodegen not found"

Install XcodeGen: `brew install xcodegen`. It must be in your PATH.

### Missing import files

If an `import` tag references a file that doesn't exist, the engine will fail with a `FileNotFoundError`. Make sure any shared content directories (like `Common/Licenses/`) exist at the expected relative path from your template's `Content/` directory.

### Binary files getting corrupted

Make sure your binary file extensions (`.png`, `.jpg`, `.zip`, etc.) are **not** listed in `parametrizableFiles`. Only list text file patterns there. Files not matching any pattern are copied verbatim.

### Extra blank lines in output

The engine strips newlines around `if`/`for`/`else`/`end`/`import` tags, but only when the tag is on its own line. If a tag is inline with other text, newlines are preserved. Put control-flow tags on their own lines for clean output.

### Parameter not being substituted

Check that:
1. The parameter `id` in `Bootstrapp.json` matches the variable name in your template exactly (case-sensitive).
2. The parameter has a value — string parameters with no default and no user input will be `nil` and produce no output.
3. The file matches a pattern in `parametrizableFiles` — files not matching any pattern are copied as-is without template rendering.
