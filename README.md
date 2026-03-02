# Over Slot

**The MLB Draft Podcast Website**

Over Slot is a comprehensive baseball scouting and analysis platform focused on MLB draft prospects. The site serves as the digital home for the Over Slot podcast, featuring in-depth player rankings, scouting reports, and analytical articles about baseball's future stars.

## Key Features

**Passwordless Authentication System**
Rather than implementing traditional username/password authentication, Over Slot uses magic link authentication exclusively. This decision eliminates password-related security vulnerabilities while providing a frictionless user experience. Users receive secure, time-limited links via email that grant access without requiring password management. The system integrates django-allauth with django-sesame to provide 24-hour token validity, balancing security with user convenience.

**Historical Ranking Preservation**
Unlike most draft sites that overwrite previous rankings, Over Slot preserves the complete history of how prospect evaluations evolve over time. The PlayerRanking model creates immutable snapshots of player assessments within specific ranking contexts, allowing visitors to track how a prospect's stock rises or falls throughout the draft cycle. This historical perspective provides valuable insight into scouting development and prediction accuracy.

**Denormalized Data Architecture**
Player information is intentionally denormalized between the Player and PlayerRanking models. While this creates some data redundancy, it serves a critical purpose: preserving the exact context of how a player was described at the time of each ranking. A player's listed school or position might change between rankings, and this architecture ensures those historical details remain accurate rather than being retroactively updated.

**Integrated Content Ecosystem**
Articles can reference multiple players and rankings through many-to-many relationships, creating a web of interconnected content. This allows readers to discover related analysis naturally - when reading about a specific prospect, they can easily find all rankings and articles that mention that player. The reverse is also true: rankings display associated articles, creating multiple pathways for content discovery.

## Core Models

**Player Model**
The Player model serves as the canonical representation of baseball prospects, storing biographical and identifying information that persists across multiple rankings. Key design decisions include using UUIDs as primary keys for external API integration and maintaining separate fields for MLB IDs and FanGraphs IDs to support future data partnerships.

**Ranking Model**
Rankings represent distinct draft boards or prospect lists, uniquely identified by year, type, and whether they represent final evaluations. The model supports multiple ranking variants per year (mid-season updates, mock drafts, final boards) through boolean flags and versioning fields. Each ranking can contain rich editorial content through integrated prose editing.

**PlayerRanking Model**
This through model captures a player's specific placement within a ranking context. The deliberate denormalization of player details (position, school, country) ensures historical accuracy when these details change over time. The model includes scouting-specific fields like role projections, risk assessments, and detailed scouting reports.

**PlayerRankingCarryingTool Model**
Scouting tools (hitting ability, power, speed, arm strength, etc.) are modeled as separate entities with grades and descriptions. This flexible approach accommodates different scouting methodologies and allows for detailed tool-by-tool analysis that goes beyond simple numerical grades.

**Article Model**
Articles serve as the editorial backbone, featuring rich text content through django-prose-editor. The many-to-many relationship with players enables comprehensive tagging that automatically creates content connections. The publish boolean provides content workflow control for draft management.

## Site Architecture

**URL Design Philosophy**
The site uses SEO-friendly slug-based URLs that prioritize readability and content discovery. Rather than exposing database IDs, all content URLs use descriptive slugs that incorporate UUIDs for uniqueness while maintaining human-readable paths. This approach supports both search engine optimization and intuitive user navigation.

**Template Architecture**
The template system emphasizes content relationships over isolated pages. Ranking detail pages prominently display associated articles, while player pages aggregate all rankings and articles mentioning that prospect. This interconnected approach encourages content exploration and provides comprehensive context for each piece of information.

**Search Implementation**
Real-time search functionality queries across all content types simultaneously, returning categorized results that maintain context. The search specifically includes cross-referential queries - rankings containing matching players are surfaced even when the ranking title doesn't match the search term. This approach recognizes that users often search for players while seeking ranking information.

## Security

**Magic Link Security Model**
The passwordless approach eliminates several attack vectors including password reuse, brute force attempts, and credential stuffing. Magic links use cryptographically secure tokens with built-in expiration, reducing the window of vulnerability compared to permanent passwords. Email delivery provides an additional authentication factor since access requires control of the registered email account.

**Subscription-Based Access Control**
The custom subscription_required decorator implements flexible access control that distinguishes between authenticated users and staff members. Non-subscribers can access preview versions of content, providing a sampling of full functionality while encouraging subscription conversion. This approach balances content protection with user acquisition.

**Content Preview System**
Rather than implementing hard paywalls, the system provides contextual previews that maintain SEO value while encouraging subscription. Preview templates include sufficient content for search engine indexing but truncate or limit interactive features for non-subscribers.

## Content Management

**Editorial Workflow**
The publish boolean on articles enables draft-to-publication workflow management. Content creators can save work in progress without immediately making it public, while the boolean provides simple on/off publishing control. This approach prioritizes editorial control over complex approval workflows.

**Rich Text Integration**
django-summernote provides a rich content creation environment with inline image uploads (stored to Spaces/S3 via default storage) and easy embeds (YouTube, Twitter/X). The configuration emphasizes essential formatting and media insertion while keeping content secure.

**Bulk Data Management**
[Human will update this section soon - involves custom management commands for spreadsheet imports]

**Admin Interface Customization**
The Django admin is extensively customized for baseball-specific workflows. Inline editing of PlayerRanking objects within Ranking administration allows for efficient ranking creation and updates. Autocomplete fields reduce data entry errors while maintaining referential integrity.

## Design

**Dark Mode First**
The interface uses dark backgrounds (#111111) as the primary design choice rather than offering theme switching. This decision reflects the target audience's preference for extended reading sessions and creates a distinctive visual identity that stands apart from typical sports sites.

**Typography Hierarchy**
Aleo serif font for headings creates distinctive character while maintaining readability. The choice of serif typography for a sports site is intentional - it suggests authority and analysis rather than breaking news, aligning with the site's focus on deep scouting content.

**Baseball Field Integration**
The custom SVG baseball field hero section isn't decorative but functional - it immediately establishes the site's focus while providing visual interest. The field design uses authentic proportions and styling to appeal to baseball enthusiasts who appreciate attention to detail.

**Responsive Grid System**
Content layouts adapt to screen size while maintaining optimal reading experiences. Player cards, ranking displays, and article previews use flexible grids that prioritize content hierarchy regardless of device constraints.

## Development and Getting Started

**Local Development Environment**

The development setup reflects the site's production architecture choices. You'll need PostgreSQL rather than SQLite because the application uses PostgreSQL-specific features and the data relationships benefit from a full relational database even in development.

**Prerequisites**
- Python 3.9 or higher
- PostgreSQL 12 or higher
- Git

**Initial Setup**

1. **Clone and Environment Setup**
```bash
git clone [repository-url]
cd overslot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Database Configuration**
Create a PostgreSQL database named `overslot` with a user `overslot` (no password required for local development):
```bash
createdb overslot
createuser overslot
```

3. **Environment Variables**
Create a `.env` file in the project root. The magic link authentication requires email configuration even in development:
```bash
DEBUG=True
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://overslot@localhost:5432/overslot

# Email configuration (required for magic links)
MAILGUN_API_KEY=your-mailgun-key
MAILGUN_SENDER_DOMAIN=your-domain.com
DEFAULT_FROM_EMAIL=noreply@your-domain.com

# For development, you can use console backend:
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

# Optional: Valkey/Redis for caching (if unset, uses in-memory cache locally)
# VALKEY_URL=valkey://localhost:6379/0
```

4. **Database Setup**
```bash
python manage.py migrate
python manage.py createsuperuser
```

**Development Workflow**

**Data Loading**
[Human will update this section soon - involves custom management commands for importing ranking data from spreadsheets]

**Content Creation**
While you can create content through the Django admin, understanding the data relationships is crucial:

- Create Players first with basic biographical information
- Create Rankings with year, type, and metadata
- Add PlayerRanking objects to connect players to specific rankings with their rank and scouting details
- Create Articles that reference players to build content connections

**Magic Link Testing**
In development with console email backend, magic links appear in your terminal output. Copy the full link including the token parameter to test authentication flow.

**Static File Handling**
The project uses DigitalOcean Spaces for static file storage in production. For development, standard Django static file handling applies:
```bash
python manage.py collectstatic
```

**Testing**

The application includes a comprehensive test suite covering authentication, UI functionality, and integration workflows. The test suite is designed to verify the unique architectural decisions of Over Slot, particularly the magic link authentication system and interconnected content relationships.

**Test Categories**
- **Authentication Tests**: Magic link generation, email sending, token validation, user creation and login workflows
- **View Tests**: All page rendering, URL routing, subscription access control, template functionality
- **Search Tests**: Real-time search across content types, JSON API responses, cross-referential queries
- **Integration Tests**: End-to-end user workflows, content discovery paths, subscription enforcement
- **Security Tests**: CSRF protection, XSS prevention, access control verification
- **Performance Tests**: Large dataset handling, search performance, relationship queries

**Running Tests**
Use the test runner script for convenient test execution:
```bash
# Run all tests
./bin/run_tests.sh

# Run specific test categories
./bin/run_tests.sh auth         # Authentication tests only
./bin/run_tests.sh views        # View and template tests
./bin/run_tests.sh search       # Search functionality tests
./bin/run_tests.sh integration  # End-to-end workflows
./bin/run_tests.sh quick        # Fast unit tests only

# See all options
./bin/run_tests.sh help
```

**Test Architecture**
The test suite uses Django's TestCase framework with mocked external services (Mailgun email delivery). Tests create realistic data scenarios including players, rankings, articles, and user accounts to verify functionality under conditions that mirror production usage.

Key testing approaches include:
- Magic link authentication flows with mocked email delivery
- Content relationship integrity across model operations
- Subscription decorator behavior for different user types
- Search functionality with various query types and edge cases
- Template rendering with authentic data relationships
- Performance testing with larger datasets

The tests prioritize verification of Over Slot's unique features rather than generic Django functionality, focusing on areas where architectural decisions create specific requirements or potential failure points.

**Production Deployment Considerations**

**Database Migration Strategy**
The denormalized data architecture means migrations require careful consideration. When player information changes, historical PlayerRanking records should retain their original values rather than cascading updates.

**Email Infrastructure**
Magic link authentication depends entirely on reliable email delivery. Mailgun integration provides delivery tracking and bounce handling that's essential for passwordless authentication to function properly.

**Static Asset Pipeline**
Player photos and other media assets require CDN distribution for acceptable performance. The DigitalOcean Spaces integration handles this automatically but requires proper configuration of CORS and public access policies.

**Caching**

The site caches expensive querysets and computed data to improve performance under logged-in traffic. Only data that is identical for all users is cached—never user-specific state—so there is no risk of showing one user's content to another.

**Environment Variable**
- **`VALKEY_URL`** – When set, the site uses Valkey (Redis-compatible) for caching. If unset, production falls back to database cache; development falls back to in-memory cache.
- Format: `valkey://host:port/0` or `valkey://:password@host:port/0`
- For TLS: `valkeys://host:port/0`

**Cached Content**

| Location | Cached Data | TTL |
|----------|-------------|-----|
| **Homepage** | Stock watch carousel, articles carousel, rankings carousel, games carousel, scouting articles, non-scouting articles, current/archived rankings, rankings count, player videos, featured games, podcasts | 5 min |
| **Articles list** | Combined news items (articles + stock watch), recent rankings sidebar | 5 min |
| **Article detail** | Article with active players/teams (per slug) | 5 min |
| **Stock watch detail** | Article with stock watch players and statlines (per slug) | 5 min |
| **Rankings list** | Current + archived rankings | 10 min |
| **Mock drafts list** | Published mock drafts | 10 min |
| **Ranking detail** | Player rankings, filter values, recent articles (per slug) | 10 min |
| **Mock draft detail** | Same as ranking detail (per slug) | 10 min |

**Other cache usage**
- Rate limiting (security) uses the same cache backend

**Automatic cache invalidation**

Saving content in the admin triggers cache invalidation:

| Model | Caches invalidated |
|-------|---------------------|
| Article | Article detail, articles list, homepage |
| Article.players / Article.teams (M2M) | Article detail, articles list, homepage |
| StockWatchArticle | Stock watch detail, articles list, homepage |
| StockWatchPlayer | Stock watch detail |
| Ranking | Ranking detail, rankings list, articles sidebar, homepage |
| PlayerRanking | Ranking detail |
| Game | Homepage |
| Player | Homepage |
| PodcastEpisode | Homepage |

**Manual cache busting**

Staff users see a "Bust homepage cache" option in the user dropdown (top right). This clears all homepage caches. Use it when you want to ensure the homepage shows fresh content immediately after publishing.

**Troubleshooting**

1. **Verify which cache backend is in use**  
   Staff users see a small badge in the top nav: **VALKEY** (green), **DB** (yellow), **LOCAL** (blue), or **OTHER** (gray).

2. **Check cache backend from shell**
   ```bash
   django-admin shell -c "from django.conf import settings; print(settings.CACHES['default']['BACKEND'])"
   ```

3. **Verify VALKEY_URL is set**
   ```bash
   echo $VALKEY_URL   # or in .env: grep VALKEY_URL .env
   ```

4. **Connection issues**  
   If Valkey is configured but the badge shows DB or OTHER, or you see 500s on cache-heavy pages:
   - Valkey/Redis service is running and reachable
   - For TLS, use `valkeys://` not `valkey://`
   - Firewall/network allows access to the Valkey port
   - **DigitalOcean App Platform**: Add the managed Valkey database as a component to your app (link it in the App Spec) so the connection string is injected and networking is configured. Private hostnames require the DB to be in the same project. If using a manually set `VALKEY_URL` with a private hostname, ensure the app and DB can reach each other.

5. **Stale content after save**  
   If content doesn't update after saving in admin:
   - Check that signals are loaded (e.g. `overslot.signals` is imported in `overslot/__init__.py`)
   - Use "Bust homepage cache" for homepage-specific issues
   - Wait for TTL (5–10 min) or restart the app to clear in-memory caches

6. **Database cache**  
   When using database cache, ensure the cache table exists:
   ```bash
   django-admin createcachetable
   # or
   django-admin setup_cache  # project-specific command
   ```

**Search Performance**
The real-time search across multiple models can become expensive with large datasets. Consider implementing database indexes on commonly searched fields and potentially moving to dedicated search infrastructure (Elasticsearch) as content volume grows.

**Debugging Common Issues**

**Magic Link Problems**
If magic links aren't working, verify email backend configuration and check that the SECRET_KEY remains consistent between link generation and validation. Token validity depends on cryptographic consistency.

**Ranking Display Issues**
Player rankings not displaying correctly usually indicates problems with the PlayerRanking through model relationships. Verify that rank values are properly set and that player foreign keys are correctly established.

**Admin Interface Performance**
Large rankings with many PlayerRanking inline objects can slow the Django admin significantly. The admin is configured with reasonable limits, but very large datasets may require custom admin interfaces or bulk editing approaches.

**Content Relationship Debugging**
If articles aren't showing expected player connections, verify that the many-to-many relationships are properly saved. The admin interface's autocomplete fields should prevent most relationship errors, but manual debugging may require checking the through tables directly.

This development approach prioritizes understanding the application's unique architectural decisions over generic Django setup. The passwordless authentication, historical data preservation, and content interconnection patterns require specific understanding to develop and maintain effectively.

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
- **django-summernote**: Rich text editing with image uploads and embeds

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

## 🧩 Feature Flags

Feature flags let us ship code safely and selectively expose features to users. This project includes a `FeatureFlag` model, Django admin integration, and template/Python helpers.

- **Model**: `FeatureFlag` with fields: `key` (slug, unique), `name`, `description`, `staff_only` (bool), `general_availability` (bool), `rollout_percentage` (0/5/25/50), `users` (M2M allow-list), `active`.
- **Logic precedence**:
  - If `general_availability` is true → enabled for everyone
  - Else if `staff_only` is true → enabled only for staff
  - Else if user is explicitly in `users` → enabled
  - Else → disabled
- **Helpers**:
  - Python: `FeatureFlag.enabled(key, user)` and instance method `is_enabled_for(user)`
  - Templates: `{% feature_enabled 'flag_key' as var %}` and `{% if_feature 'flag_key' 'then' 'else' %}`

### How engineers should gate features

1) Pick a stable `key` for your feature (e.g., `new_homepage_belt`).

2) Gate in templates:

```django
{% load overslot_tags %}
{% feature_enabled 'new_homepage_belt' as show_belt %}
{% if show_belt %}
  <!-- New experience -->
  <section class="belt"> ... </section>
{% else %}
  <!-- Fallback experience -->
  <section class="belt--legacy"> ... </section>
{% endif %}
```

Inline alternative for small text substitutions:

```django
{% load overslot_tags %}
<h2>{% if_feature 'new_homepage_belt' 'New Belt' 'Belt' %}</h2>
```

3) Gate in Python (views, utils, etc.):

```python
from overslot.models import FeatureFlag

def view(request):
    if FeatureFlag.enabled('new_homepage_belt', request.user):
        # serve new experience
        ...
    else:
        # serve legacy experience
        ...
```

Notes:
- If a flag with that `key` does not exist, `FeatureFlag.enabled(...)` returns False (feature remains hidden by default).
- Prefer gating at the narrowest point needed (template fragment or specific code path) to minimize complexity.

### How admins enable and manage flags

1) In Django Admin, go to `Feature Flags` → `Add`.
- Set `key` to exactly match what templates/code expect (e.g., `new_homepage_belt`).
- Optionally set `name` and `description` for clarity.

2) Choose visibility mode:
- **General availability**: check `general_availability` to show to everyone.
- **Staff only**: check `staff_only` to limit to staff accounts.
- **Allow-list**: add specific users to the `users` field.
- **Percentage rollout**: pick `rollout_percentage` (5/25/50). Then use the admin action “Assign rollout users based on percentage (replace current)” to populate the `users` list. Re-run this action after changing the percentage.

3) Toggle `active` to quickly disable the flag entirely if needed.

Precedence reminders:
- `general_availability` overrides all other controls.
- `staff_only` takes precedence over any non-staff `users` allow-list membership.

### Rollout best practices

- Start with `staff_only` to validate internally.
- Move to a small `rollout_percentage` and click the admin action to assign a random cohort.
- Monitor, then increase to 25%/50% as confidence grows.
- Finally, set `general_availability` to true and optionally clear the allow-list.

### Troubleshooting

- Seeing legacy UI? Confirm the flag exists, is `active`, and your user matches the visibility rules.
- Percentage changed but audience didn’t? Re-run the “Assign rollout users…” admin action to refresh the cohort.
- Template key mismatch? Ensure the admin `key` exactly matches the string used in templates/Python.
