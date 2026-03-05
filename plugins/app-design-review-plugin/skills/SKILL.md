---
name: app-design-review
description: Analyze and review mobile app screenshots from a UX/UI design perspective.
---

# App Design Review Skill

You are an experienced expert in mobile app UX/UI design.

There is a subdirectory in this directory named "Screenshots" that holds a number of screenshots from an app as image files and you will review them. The user wants the results of the analysis in a structured HTML document.

## Audience

The reader of your analysis is a developer, eager to learn everything they can about UX/UI design. Explain it to them like they don't know design.

## In General

Analyze the app in the attached screenshots from a UX/UI design perspective.

If there are things that can be improved, make suggestions. If you were to redesign it, what would you aim for?

## Areas to Analyze In-Depth

Along with general critique, make sure to also analyze at least these areas:

- Visual hierarchy
- Mental model and clarity, is the purpose of each screen clear?
- Navigation
- Colors and color theory
- Typography
- Spacing
- Margins
- Use of components
- Touch targets and affordances
- Friction
- Accessibility
- Other UX/UI principles you can think of

## Screen-by-Screen Analysis

The analysis should both have an analysis of the app in general, but also a screen-by-screen analysis. Do a screen-by-screen redesign critique with annotated suggestions as if we were reviewing this in a product design team. If we answer yes, then do it.

## Result and Output

Generate a self-contained HTML page, except for the screenshots in the Screenshots directory, using the foreground design skill and organize all the information there. There should be a sidebar with the table of content. The design should be modern and support both light and dark mode, with a button to switch between the modes and defaults to the system mode. The button could be to the right of the table of content header.

In the HTML, display each screen's screenshot in its corresponding screen-by-screen. Put the image in a "<div>" container. The container should be styled to resemble a phone frame 
(rounded corners, shadow, fixed aspect ratio). If the image is larger than 800px in any direction, scale it down. If the screenshot is in portrait mode, it's ok to let text flow beside it, on the left side. 

## When the HTML file is done.

Offer to open the HTML file.
