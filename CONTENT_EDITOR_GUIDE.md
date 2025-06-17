# Overslot Content Editor Guide

*A comprehensive guide for managing articles, rankings, and homepage content*

## Table of Contents
1. [Getting Started with Django Admin](#getting-started-with-django-admin)
2. [Managing Articles](#managing-articles)
3. [Managing Rankings](#managing-rankings)
4. [Controlling the Homepage](#controlling-the-homepage)
5. [Working with Drafts vs Published Content](#working-with-drafts-vs-published-content)
6. [Managing Featured Images](#managing-featured-images)
7. [Best Practices](#best-practices)

---

## Getting Started with Django Admin

### What is Django Admin?
Django Admin is a web-based interface that lets you manage your website's content without needing to know code. Think of it as your content management dashboard.

### Accessing the Admin
1. Navigate to your website's admin URL (typically `/admin/`)
2. Log in with your editor credentials
3. You'll see a dashboard with different content types you can manage

### Basic Admin Interface Concepts

**List View**: Shows all items of a type (e.g., all articles) in a table format
- You can search, filter, and sort items
- Some fields can be edited directly in the list (these show as form fields instead of plain text)
- Click on an item's title to open the detailed edit view

**Edit View**: Detailed form for creating or editing a single item
- Fill out all relevant fields
- Use the "Save" button to save changes
- Use "Save and continue editing" to save and stay on the same page
- Use "Save and add another" to save and immediately create a new item

---

## Managing Articles

### Creating a New Article

1. Go to the **Articles** section in the admin
2. Click **"Add Article"**
3. Fill out the required fields:

#### Essential Fields
- **Headline**: The main title of your article (required)
- **Subhead**: A secondary headline that provides more context (optional but recommended)
- **Blurb**: A brief summary or teaser text (appears in article lists and previews)
- **Body**: The main content of your article

#### Publishing Controls
- **Publish**: Check this box to make the article visible to website visitors
  - ⚠️ **Important**: Unchecked = Draft (only visible to staff), Checked = Live on website
- **Is Carousel**: Check this box to feature the article on the homepage carousel

#### Additional Options
- **Authors**: Link the article to author profiles (for bylines)
- **Players**: Tag players mentioned in the article (creates automatic links)
- **Featured Image**: Upload an image to display with the article
- **Slug**: The URL-friendly version of your headline (auto-generated, usually don't need to change)

### Editing Existing Articles

#### Quick Edit (List View)
From the Articles list, you can quickly toggle:
- **Publish status**: Check/uncheck to publish/unpublish
- **Carousel status**: Check/uncheck to add/remove from homepage

#### Full Edit
Click on an article's headline to open the full editor where you can modify all content.

### Article Content Tips

#### Writing Body Content
The body editor supports rich formatting:
- **Bold**, *italic*, ~~strikethrough~~, and underline text
- Headers (H1, H2, H3, etc.)
- Bullet points and numbered lists
- Blockquotes for highlighting key information
- Tables for data presentation
- You can switch to HTML view for advanced formatting

#### Headline Best Practices
- Keep headlines under 60 characters when possible
- Make them descriptive and engaging
- Use title case (capitalize major words)

#### Subhead Guidelines
- Use subheads to provide additional context
- They should complement, not repeat, the headline
- Great for adding details like "Draft Analysis" or "Scouting Report"

#### Blurb Writing
- Keep to 1-2 sentences
- Summarize the key point or hook of the article
- This text appears in previews and social media shares

---

## Managing Rankings

### Understanding Rankings vs Articles
**Important**: You don't create rankings themselves (those are loaded automatically with player data). Your job is to add the editorial content that makes rankings engaging and informative.

### Editing Ranking Content

1. Go to the **Rankings** section in the admin
2. Find the ranking you want to edit (search by year or type)
3. Click on the ranking to open the editor

#### Key Fields You Control

**Editorial Content**:
- **Headline**: Create an engaging title for the ranking (e.g., "2024 Draft Preview: Top 100 Prospects")
- **Subhead**: Add context or key themes (e.g., "Pitching depth drives this year's class")
- **Blurb**: Write a compelling summary of the ranking's key insights
- **Body**: Write detailed analysis, methodology, or commentary

**Visual Elements**:
- **Featured Image**: Upload a hero image for the ranking

**Publishing Controls**:
- **Publish**: Make the ranking visible to site visitors
- **Is Carousel**: Feature on the homepage

#### Technical Fields (Usually Pre-Set)
These are typically set automatically, but you should understand them:
- **Year**: The draft year or ranking period
- **Ranking Type**: College, High School, or International
- **Ranking Length**: How many players (e.g., "100", "50")
- **Is Final**: Whether this is the final version before the draft

### Ranking Content Strategy

#### Headlines for Rankings
- Include the year and scope: "2024 Top 100 Draft Prospects"
- Add editorial angle: "2024 MLB Draft: Pitching Takes Center Stage"
- Make it specific: "College Draft Rankings: Final Top 50"

#### Body Content Ideas
- **Methodology**: Explain how players were evaluated
- **Key Themes**: Discuss trends in the class (e.g., "strength of college pitching")
- **Notable Risers/Fallers**: Highlight significant changes from previous rankings
- **Regional Analysis**: Break down talent by geographic area
- **Position Breakdowns**: Analyze strength at different positions

---

## Controlling the Homepage

The homepage displays featured content in two main areas:

### Homepage Carousel
**What it shows**: A rotating banner featuring your most important content
**How to control it**: Use the **"Is Carousel"** checkbox on articles and rankings

#### Carousel Strategy
- **Limit carousel items**: Only feature your best, most current content
- **Mix content types**: Include both articles and rankings
- **Keep it fresh**: Regularly update which items are featured
- **Order matters**: Most recently created carousel items appear first

#### Quick Carousel Management
1. Go to Articles or Rankings list view
2. Use the **Is Carousel** checkbox column to quickly add/remove items
3. Changes take effect immediately

### Homepage Content Sections
The homepage also shows:
- **Latest Articles**: Recent articles marked for carousel
- **Latest Ranking**: Most recent ranking marked for carousel
- **Article List**: All published carousel articles
- **Rankings List**: All published carousel rankings

### Homepage Curation Best Practices

#### What to Feature
- ✅ **Latest rankings**: Always feature your most current draft board
- ✅ **Breaking news articles**: Time-sensitive content
- ✅ **Major analysis pieces**: In-depth scouting reports or trend analysis
- ✅ **Seasonal content**: Draft previews, season wrap-ups, etc.

#### What NOT to Feature
- ❌ **Old content**: Remove outdated rankings and articles
- ❌ **Minor updates**: Small corrections or brief news items
- ❌ **Test content**: Draft articles you're still working on

---

## Working with Drafts vs Published Content

### Understanding Publication Status

#### Draft Status (Publish = Unchecked)
- **Visible to**: Staff members only
- **Appears on**: Admin interface only
- **Use for**: Work-in-progress content, future-dated articles, content awaiting review

#### Published Status (Publish = Checked)
- **Visible to**: All website visitors
- **Appears on**: Public website, search engines, social media
- **Use for**: Final, ready-to-publish content

### Draft Workflow Best Practices

#### Creating Content
1. **Start as Draft**: Always create new content with Publish unchecked
2. **Review Process**: Complete all writing and editing while in draft
3. **Final Check**: Verify all fields are complete (headline, blurb, featured image, etc.)
4. **Publish**: Check the Publish box only when completely ready

#### Content Review
Before publishing, ask yourself:
- Is the headline compelling and accurate?
- Does the blurb effectively summarize the content?
- Is there a featured image if needed?
- Are all player tags and author attributions correct?
- Is the content factually accurate and well-written?

### Managing Published Content

#### Making Changes to Live Content
- ✅ **Minor edits**: Fix typos, update small details
- ⚠️ **Major changes**: Consider unpublishing, editing, then republishing
- ❌ **Avoid**: Making significant changes that might confuse readers who already read the original

#### Unpublishing Content
Sometimes you need to remove content from the public site:
- Uncheck the **Publish** box
- Content becomes draft-only immediately
- Useful for: Corrections, outdated information, seasonal content

---

## Managing Featured Images

### When to Use Featured Images

#### Always Use For:
- Major ranking releases
- In-depth analysis articles
- Player spotlight pieces
- Seasonal content (draft previews, etc.)

#### Optional For:
- Brief news updates
- Minor ranking adjustments
- Quick analysis pieces

### Image Guidelines

#### Technical Requirements
- **Format**: JPG or PNG preferred
- **Size**: Recommended minimum 1200x600 pixels
- **Aspect Ratio**: 2:1 (landscape) works best for most layouts

#### Content Guidelines
- **Relevant**: Image should relate to the article/ranking content
- **High Quality**: Use professional or high-resolution images
- **Rights**: Only use images you have permission to use
- **Players**: Individual player photos work great for player-focused content
- **Action Shots**: Game photos, draft ceremonies, training footage
- **Graphics**: Custom graphics, logos, or branded imagery

### Uploading Images

1. In the article or ranking editor, find the **Featured Image** field
2. Click **"Choose File"** or **"Browse"**
3. Select your image from your computer
4. The image will upload automatically when you save
5. Preview how it looks on the site

---

## Best Practices

### Content Planning

#### Editorial Calendar
- **Plan major content**: Schedule ranking releases around key dates
- **Seasonal themes**: Draft prep, season previews, year-end reviews
- **Regular content**: Maintain consistent publishing schedule

#### Content Mix
- **Balance articles and rankings**: Don't over-feature one type
- **Vary content depth**: Mix quick updates with in-depth analysis
- **Geographic diversity**: Cover different regions and levels

### SEO and Discoverability

#### Headlines
- Include relevant keywords naturally
- Make them descriptive and specific
- Avoid clickbait; focus on accuracy

#### Blurbs
- Write complete sentences
- Include key terms readers might search for
- Make them compelling enough to encourage clicks

### Quality Control

#### Before Publishing Checklist
- [ ] Headline is compelling and accurate
- [ ] Subhead adds value (if used)
- [ ] Blurb effectively summarizes content
- [ ] Body content is complete and well-formatted
- [ ] Featured image is appropriate and high-quality
- [ ] Author and player tags are correct
- [ ] Content is factually accurate
- [ ] Spelling and grammar are correct

#### Regular Maintenance
- **Weekly**: Review carousel items, remove outdated content
- **Monthly**: Check for broken links, outdated information
- **Seasonally**: Archive old rankings, update evergreen content

### Working Efficiently

#### Keyboard Shortcuts
Most browsers support these in the admin:
- `Ctrl+S` (or `Cmd+S` on Mac): Save current item
- `Ctrl+Z`: Undo last change
- `Tab`: Move between form fields

#### Batch Operations
- Use list view editing for quick status changes
- Filter and search to find content quickly
- Use "Save and add another" for creating multiple similar items

#### Content Templates
Develop templates for common content types:
- **Ranking Release**: Standard structure for new rankings
- **Player Spotlight**: Consistent format for player features
- **News Update**: Quick format for breaking news

---

## Troubleshooting

### Common Issues

#### "Content not appearing on website"
- Check that **Publish** is checked
- Verify **Is Carousel** is checked if it should appear on homepage
- Clear browser cache and refresh

#### "Changes not showing"
- Make sure you clicked **Save**
- Check if you're in the right environment (draft vs. live)
- Browser cache may need clearing

#### "Can't upload image"
- Check file size (keep under 5MB)
- Verify file format (JPG, PNG, GIF)
- Try a different browser

### Getting Help

- **Technical Issues**: Contact your site administrator
- **Content Questions**: Refer to this guide or ask your editorial team
- **Training**: Request additional training sessions if needed

---

*Last updated: [Current Date]*
*For questions about this guide, contact your site administrator.* 