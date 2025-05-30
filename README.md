# Over Slot
**The MLB Draft Podcast Website**

Over Slot is a comprehensive baseball scouting and analysis platform focused on MLB draft prospects. The site serves as the digital home for the Over Slot podcast, featuring in-depth player rankings, scouting reports, and analytical articles about baseball's future stars.

## 🎯 Mission

To provide the most comprehensive and insightful coverage of MLB draft prospects through detailed scouting reports, interactive rankings, and expert analysis that helps fans, scouts, and industry professionals understand the next generation of baseball talent.

## ✨ Key Features

### 🔐 Passwordless Authentication
- **Magic Link Only**: Users sign in and create accounts exclusively via secure magic links sent to their email
- **No Passwords**: Completely passwordless experience for enhanced security and user convenience
- **Email Verification**: Integrated with django-allauth for seamless user management
- **24-Hour Token Validity**: Magic links remain valid for 24 hours for user convenience

### ⚾ Baseball-Focused Content Management
- **Player Rankings**: Dynamic draft boards with detailed prospect rankings
- **Scouting Reports**: In-depth analysis and player profiles
- **Articles**: Editorial content linking players, rankings, and analysis
- **Carrying Tools**: Detailed scouting metrics and player evaluations

### 🎨 Professional Design
- **Dark Mode Interface**: Sleek, modern design optimized for readability
- **Red Brand Theme**: Consistent baseball-inspired color scheme (#ef4444)
- **Baseball Field Hero**: Custom SVG hero section with authentic field design
- **Responsive Layout**: Optimized for desktop, tablet, and mobile devices
- **Fixed Navigation**: Persistent navigation with integrated search functionality

### 🔍 Advanced Search
- **Real-time Search**: Instant search across articles, rankings, and players
- **Categorized Results**: Organized search results by content type
- **Player Tags**: Easy navigation between related content

## 🛠 Technology Stack

### Backend
- **Django 5.2**: Modern Python web framework
- **PostgreSQL**: Robust relational database
- **django-allauth 65.8.1**: Authentication and account management
- **django-sesame 3.2.3**: Magic link authentication
- **django-prose-editor**: Rich text editing for content creation

### Frontend
- **Bulma CSS Framework**: Modern, responsive CSS framework
- **Custom SVG Graphics**: Hand-crafted baseball-themed illustrations
- **Font Awesome Icons**: Professional iconography
- **Google Fonts**: Aleo serif font for distinctive typography

### Infrastructure
- **Mailgun Integration**: Reliable email delivery for magic links
- **DigitalOcean Spaces**: CDN and static file storage
- **ngrok**: HTTPS proxy for development

## 📊 Data Models

### Core Models

#### Player
- **Purpose**: Individual baseball prospects and players
- **Key Fields**: Name, position, school, country, photo, biographical data
- **Relationships**: Many-to-many with rankings and articles via through models

#### Ranking
- **Purpose**: Draft boards and prospect rankings for specific years/dates
- **Key Fields**: Title, year, date, description, slug for SEO-friendly URLs
- **Features**: Supports multiple rankings per year for updated boards

#### PlayerRanking
- **Purpose**: A player's specific position within a ranking
- **Key Fields**: Rank position, scouting notes, denormalized player data
- **Benefits**: Optimized queries and historical data preservation

#### PlayerRankingCarryingTool
- **Purpose**: Detailed scouting metrics and tool grades
- **Key Fields**: Tool categories, grades, scores, detailed evaluations
- **Features**: Flexible system for various scouting methodologies

#### Article
- **Purpose**: Editorial content, analysis, and news
- **Key Fields**: Headline, content, publication date, author relationships
- **Relationships**: Can reference multiple players and rankings

### Supporting Models
- **Author**: Content creators and contributors
- **Categories**: Content organization and navigation
- **Tags**: Flexible content labeling system

## 🌐 Site Architecture

### URL Structure
```
/                           # Homepage with latest rankings and articles
/articles/                  # Paginated article listings
/articles/{slug}/          # Individual article pages
/rankings/                  # Paginated ranking listings  
/rankings/{slug}/          # Individual ranking pages with player lists
/players/{slug}/           # Player profile pages
/auth/login/               # Magic link sign-in
/auth/signup/              # Magic link account creation
/admin/                    # Django admin interface
```

### Template Structure
- **Base Template**: Responsive layout with fixed navigation and footer
- **Component Templates**: Reusable navigation, search, and UI elements
- **Content Templates**: Specialized layouts for rankings, articles, and players
- **Authentication Templates**: Custom-styled auth flows matching site design

## 🎨 Design System

### Color Palette
- **Primary Red**: #ef4444 (Theme color for accents and branding)
- **Dark Background**: #111111 (Main background)
- **Dark Surface**: #1a1a1a (Cards and elevated content)
- **Text Colors**: White primary, #94a3b8 secondary, #64748b muted

### Typography
- **Headings**: Aleo serif font for distinctive character
- **Body Text**: System font stack for optimal readability
- **Code**: Monospace font for technical content

### Visual Elements
- **Baseball Field SVG**: Custom hero section with authentic field design
- **Logo Integration**: Compact microphone and baseball stitching logo
- **Responsive Grid**: Flexible layouts adapting to all screen sizes

## 🚀 Key Features & Functionality

### Homepage
- **Hero Section**: Baseball field background with podcast branding
- **Latest Content**: Side-by-side rankings and articles
- **Player Previews**: Top prospects from recent rankings
- **Responsive Design**: Optimized for all devices

### Rankings System
- **Draft Boards**: Comprehensive prospect rankings with detailed player cards
- **Player Cards**: Photos, positions, schools, and ranking badges
- **Historical Data**: Preserved rankings show prospect development over time
- **Interactive Elements**: Hover effects and smooth animations

### Article System
- **Rich Content**: Full-featured article editor with media support
- **Player Tagging**: Articles can reference multiple players with automatic linking
- **Author Attribution**: Support for multiple authors and bylines
- **Publication Workflow**: Draft and publish states with scheduling

### Search Functionality
- **Global Search**: Search across all content types from navigation
- **Real-time Results**: Instant search with categorized results
- **Deep Linking**: Direct navigation to relevant content

### User Experience
- **Magic Link Auth**: Frictionless account creation and sign-in
- **Mobile Optimized**: Touch-friendly interface on all devices
- **Fast Loading**: Optimized images and efficient database queries
- **Accessibility**: Semantic HTML and keyboard navigation support

## 🔒 Security Features

- **Magic Link Authentication**: Eliminates password-related security risks
- **CSRF Protection**: Built-in Django security measures
- **Secure Sessions**: HTTPOnly cookies and secure session management
- **Email Verification**: Automatic email verification through magic links
- **Admin Protection**: Separate admin authentication with enhanced security

## 📱 Mobile Experience

- **Responsive Navigation**: Collapsible mobile menu
- **Touch Optimized**: Large touch targets and smooth interactions
- **Fast Loading**: Optimized for mobile networks
- **Progressive Enhancement**: Core functionality works without JavaScript

## 🎯 SEO Optimization

- **Clean URLs**: SEO-friendly slugs for all content
- **Meta Tags**: Comprehensive meta descriptions and titles
- **Semantic HTML**: Proper heading hierarchy and semantic elements
- **Performance**: Fast loading times and optimized images

## 📈 Content Management

### Admin Interface
- **Django Admin**: Full-featured content management system
- **Rich Text Editor**: Professional writing environment for articles
- **Media Management**: Image upload and optimization
- **User Management**: Author and contributor management

### Content Workflow
- **Draft System**: Articles can be saved as drafts before publication
- **Scheduling**: Future publication dates supported
- **Version Control**: Content history and revision tracking
- **Bulk Operations**: Efficient management of large datasets

## 🔧 Development Setup

[This section intentionally left blank for local development instructions]

## 📝 License

[License information to be added]

## 🤝 Contributing

[Contributing guidelines to be added]

## 📞 Contact

For questions about Over Slot or this website, please contact the development team.

---

*Over Slot - Comprehensive coverage of baseball's future stars*
