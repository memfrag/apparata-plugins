---
name: summarize-epub
description: Summarize every chapter of an epub or ibooks book into a markdown file. Use when the user wants to summarize an epub, ibooks, or ebook.
argument-hint: [path-to-epub-directory]
allowed-tools: Bash(grep:*), Bash(head:*), Bash(plutil:*)
---

# Summarize EPUB Book

You are summarizing an epub/ibooks book. The book lives in a directory with the extension `.epub` or `.ibooks`.

The target epub directory is: **$ARGUMENTS**

## Step 0: Find the book

If a path argument was provided, use it directly and skip to Step 1.

If no argument was provided, first check the current working directory and its immediate parent for `.epub` or `.ibooks` directories. If you find one or more, ask the user which one to summarize (or proceed directly if there's only one).

If no epub/ibooks directories are found nearby, ask the user whether they'd like you to search in the **Apple Books library**. If they say yes:

1. The Apple Books data directory is located at:
   ```
   ~/Library/Containers/com.apple.BKAgentService/Data/Documents/iBooks/Books
   ```

2. In that directory there is a file called `Books.plist`. It is a binary plist. To read it, run:
   ```bash
   plutil -p ~/Library/Containers/com.apple.BKAgentService/Data/Documents/iBooks/Books/Books.plist
   ```
   This outputs the contents in a JSON-like human-readable format.

3. The output contains an array of book entries. Each book entry has:
   - `"itemName"` — the display name / title of the book
   - `"path"` — the filesystem path to the actual epub file

4. Ask the user for the name (or partial name) of the book they want summarized. Then search the `plutil` output for entries whose `"itemName"` contains a case-insensitive match of what the user typed. If there are multiple matches, present them and let the user choose. If there is exactly one match, confirm it with the user.

5. Use the `"path"` value from the matched entry as the epub directory path. Note: the path may point to a `.epub` file or directory. If it's a zip file, you'll need to find the extracted directory or work with the path as-is if it's already a directory.

If the Apple Books directory doesn't exist or the plist can't be read, let the user know and ask them to provide a path manually.

## Step 1: Locate the content directory

Inside the epub directory, find the content directory. It is typically named `OEBPS` or `OPS`. Use Glob to find it:

```
<epub-dir>/OEBPS/
<epub-dir>/OPS/
```

If neither exists, look for any directory containing `.xhtml` or `.opf` files.

## Step 2: Discover the book structure

Try these approaches in order to determine chapter order and titles:

### Approach A: Parse `content.opf`

Look for a `content.opf` or `*.opf` file in the content directory. Read it. It contains:

- `<metadata>` — book title (`<dc:title>`) and author (`<dc:creator>`)
- `<manifest>` — list of all files with IDs and hrefs
- `<spine>` — the **reading order** of content items (references manifest IDs via `idref`)

Use the spine to determine which xhtml files to read and in what order. Cross-reference spine `idref` values with manifest `id` values to get file paths.

### Approach B: Parse `toc.xhtml` or `toc.ncx`

If the OPF file is missing or unhelpful:

- `toc.xhtml` (EPUB3): Look for `<nav epub:type="toc">` containing an `<ol>` with `<li><a href="...">Chapter Title</a></li>` entries.
- `toc.ncx` (EPUB2): Look for `<navMap>` containing `<navPoint>` entries with `<text>` (title) and `<content src="..."/>` (file path).

### Approach C: Infer from filenames

If no structural metadata is available, use Glob to find all `.xhtml` files in the content directory. Sort them by name (they're typically named sequentially like `chapter-001.xhtml`, `chapter-002.xhtml`, etc. or `ch01.xhtml`, `ch02.xhtml`, etc.). Read each file's `<title>` tag and `<h1>`/`<h2>` headings to determine chapter titles.

## Step 3: Identify the book title and author

Extract from the OPF metadata, the title page xhtml file, or the first xhtml file that contains a book title.

## Step 4: Read and summarize each chapter

Read every content xhtml file identified in Step 2, in reading order. Skip files that are purely structural (stylesheets, images, fonts) or contain no substantive text (e.g., a bare title page with only a title and author name, or a table of contents page).

For each chapter or section that contains substantive content:

1. Read the full xhtml file. If a file is very large, read it in chunks.
2. Write a **verbose, detailed summary** that captures:
   - The main arguments, concepts, and frameworks introduced
   - Key stories, anecdotes, and examples used to illustrate points
   - Specific advice, rules of thumb, or actionable takeaways
   - Important distinctions and definitions
   - How the chapter connects to the broader book narrative
3. Do NOT simply list bullet points. Write flowing prose paragraphs that a reader could use as a thorough substitute for reading the chapter. Include specific details from examples and stories — names, numbers, outcomes.
4. If the chapter includes sample dialogues, case studies, or step-by-step frameworks, describe them in enough detail that the reader understands the content without having read the original.

## Step 5: Write the summary file

Write the complete summary to a markdown file named `summary.md` inside the content directory (next to the xhtml files).

Format the file as follows:

```markdown
# <Book Title> — by <Author>

**Subtitle:** *<subtitle if available>*

---

## <Section/Chapter Title>

<Verbose summary paragraphs>

---

## <Next Section/Chapter Title>

<Verbose summary paragraphs>

...
```

Use `---` horizontal rules between chapters for visual separation. Use `##` for chapter headings. Use `###` for sub-sections within a chapter summary only if the chapter is very long and covers clearly distinct topics.

## Important guidelines

- **Be thorough.** Each chapter summary should be multiple substantial paragraphs. Aim for a summary that captures 70-80% of the informational content of each chapter.
- **Preserve specificity.** Include specific names, numbers, dollar amounts, company names, and outcomes from examples and anecdotes. These details make summaries useful.
- **Maintain the author's voice.** If the author uses memorable phrases, rules of thumb, or frameworks with specific names, include those exact terms.
- **Read every chapter file.** Do not skip chapters or sections. Read them all, even if there are many. Use parallel reads where possible to save time.
- **Handle large books.** If the book has many chapters, read files in parallel batches. You may need to use subagents for very large books to avoid context limits.
- **Skip non-content files.** Don't summarize the table of contents page, copyright page, dedication, or pages that contain only a title/image with no substantive text. Do summarize introductions, forewords, afterwords, conclusions, and appendices if they contain substantive content.
