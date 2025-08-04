# Over Slot Email Style Guide

## Overview
This style guide ensures consistent, accessible, and reliable email design across all Over Slot communications. Our emails are designed to work seamlessly across all email clients, including those with limited HTML/CSS support.

## Design Principles

### 1. Text-First Approach
- **Primary Goal**: Ensure content is readable even without CSS
- **Fallback**: Always provide plain text alternatives for links and buttons
- **Accessibility**: Use semantic HTML and sufficient color contrast

### 2. Email Client Compatibility
- **Target Clients**: Gmail, Outlook (all versions), Apple Mail, Yahoo Mail, Thunderbird
- **Fallback Support**: Works in text-only clients and with images disabled
- **Mobile Responsive**: Optimized for mobile viewing

### 3. Brand Consistency
- **Colors**: Consistent blue palette and neutral grays
- **Typography**: System fonts for maximum compatibility
- **Layout**: Clean, scannable structure

## Color Palette

```css
/* Primary Colors */
--primary-blue: #1d4ed8     /* Main buttons and links */
--primary-blue-hover: #1e40af   /* Button hover state */
--dark-gray: #1f2937        /* Headers and dark text */
--medium-gray: #374151      /* Body text */
--light-gray: #6b7280       /* Footer and meta text */

/* Background Colors */
--white: #ffffff            /* Main content background */
--light-bg: #f8fafc         /* Page background */
--footer-bg: #f9fafb        /* Footer background */
--info-bg: #f0f9ff          /* Info box background */

/* Border Colors */
--border-light: #e5e7eb     /* Light borders */
--border-info: #e0f2fe      /* Info box borders */
```

## Typography

### Font Stack
```css
font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
```

### Font Sizes
- **Logo**: 24px, weight 700
- **Title**: 24px, weight 600 (20px on mobile)
- **Body Text**: 16px, weight 400
- **Button Text**: 16px, weight 600 (15px on mobile)
- **Footer Text**: 14px, weight 400

## Button Styles

### Primary Button
```css
.email-button {
    background-color: #1d4ed8;
    color: #ffffff;
    padding: 16px 32px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 16px;
    text-decoration: none;
}
```

### Button Best Practices
1. **Always include `!important`** for email client compatibility
2. **Provide fallback text link** below the button
3. **Use table-based buttons** for Outlook compatibility (if needed)
4. **Test in multiple clients** before deploying

## Layout Structure

### 1. Container
- **Max-width**: 600px
- **Background**: White
- **Centered**: With auto margins

### 2. Header
- **Background**: Dark gray (#1f2937)
- **Logo**: White text, centered
- **Padding**: 24px on desktop, 20px on mobile

### 3. Content Area
- **Padding**: 32px on desktop, 20px on mobile
- **Background**: White
- **Text Color**: Medium gray (#374151)

### 4. Footer
- **Background**: Light gray (#f9fafb)
- **Border**: Top border in light gray
- **Text**: Smaller, muted color
- **Padding**: 24px on desktop, 20px on mobile

## Email Types

### 1. Authentication Emails (Magic Links)
**Purpose**: Login and signup verification
**Template**: `auth/email/magic_link.html`
**Button Text**: 
- "Sign In" (for existing users)
- "Create Account" (for new users)

### 2. Email Verification
**Purpose**: Verify secondary email addresses
**Template**: `account/email/verify_secondary_email.html`
**Button Text**: "Verify Email Address"

## Content Guidelines

### 1. Subject Lines
- **Keep under 50 characters**
- **Be specific and actionable**
- **Include brand name when relevant**

Examples:
- "Sign in to Over Slot"
- "Verify your email address - Over Slot"
- "Welcome to Over Slot!"

### 2. Body Content
- **Start with personalization** when possible
- **Use clear, action-oriented language**
- **Keep paragraphs short** (2-3 sentences max)
- **Include fallback instructions**

### 3. Call-to-Action
- **One primary action per email**
- **Button text should be verb-driven**
- **Always provide a fallback text link**

## Technical Implementation

### 1. Base Template
Use `email_base.html` as the foundation for all emails:

```html
{% extends "email_base.html" %}

{% block email_title %}Your Email Subject{% endblock %}

{% block email_content %}
    <h1 class="email-title">Your Title</h1>
    <p class="email-text">Your content...</p>
    
    <div class="email-button-container">
        <a href="{{ your_link }}" class="email-button" style="display: inline-block !important; background-color: #1d4ed8 !important; color: #ffffff !important; text-decoration: none !important; padding: 16px 32px !important; border-radius: 6px !important; font-weight: 600 !important;">
            Your Button Text
        </a>
    </div>
    
    <p class="email-text">
        <strong>Button not working?</strong> Copy and paste this link:
    </p>
    <div class="email-fallback-link">{{ your_link }}</div>
{% endblock %}
```

### 2. CSS Best Practices
- **Use `!important`** for all critical styles
- **Inline critical styles** on elements for maximum compatibility
- **Test thoroughly** in multiple email clients
- **Provide table-based fallbacks** for complex layouts if needed

### 3. Testing Checklist
- [ ] Gmail (web and mobile app)
- [ ] Outlook (web, desktop 2016+, mobile)
- [ ] Apple Mail (macOS and iOS)
- [ ] Yahoo Mail
- [ ] With images disabled
- [ ] Text-only view
- [ ] Dark mode (where supported)

## Accessibility

### 1. Color Contrast
- **Text on white**: Minimum 4.5:1 contrast ratio
- **Button text**: White on dark blue provides 8.2:1 contrast
- **Never rely on color alone** to convey information

### 2. Alt Text
- **Logo**: "Over Slot"
- **Buttons**: Include meaningful alt text for any button images

### 3. Structure
- **Use semantic HTML** (`<h1>`, `<p>`, etc.)
- **Logical reading order** without CSS
- **Descriptive link text** (avoid "click here")

## Version History
- **v1.0** (Current): Initial comprehensive style guide with text-first approach
- Established consistent color palette and typography
- Created reusable base template
- Optimized for maximum email client compatibility