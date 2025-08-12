# 🎵 Spotilytics

A comprehensive Spotify analytics dashboard that provides deep insights into your music listening habits. Built with Django and modern web technologies, Spotilytics transforms your Spotify data into beautiful visualizations and meaningful statistics.

## 🎯 What is Spotilytics?

Spotilytics is a full-stack web application that connects to your Spotify account to analyze and visualize your music listening patterns. It offers detailed statistics, interactive charts, AI-powered insights, and music discovery features about your musical preferences and habits.

### ✨ Key Features

- **📊 Real-time Data Sync**: Automatic background synchronization of listening history using Celery
- **🎛️ Interactive Dashboard**: Comprehensive overview of your listening statistics with dynamic time range filtering
- **📈 Advanced Analytics**: Deep dive into artist, album, track, and genre statistics with multiple chart types
- **🤖 AI Chat Assistant**: OpenAI-powered chatbot that can answer questions about your music data
- **🔍 Music Search & Discovery**: Explore new music and see detailed information about tracks, artists, and albums
- **🎵 Personalized Recommendations**: AI-generated music suggestions based on your listening history
- **🆕 New Releases Tracking**: Stay updated with the latest releases from your favorite artists
- **📱 Responsive Design**: Modern UI that works seamlessly across desktop and mobile devices

## 🛠️ Technologies Used

### Backend

- **🐍 Python 3.10+** - Core programming language
- **🌐 Django 5.1** - Web framework
- **🔗 Spotify API** - API development
- **🐘 PostgreSQL** - Primary database
- **🔥 Redis** - Caching and session storage
- **⚡ Celery** - Background task processing
- **🚀 aiohttp** - Asynchronous HTTP client for Spotify API

### Frontend

- **🎨 HTML5/CSS3** - Modern responsive design
- **⚡ JavaScript (ES6+)** - Interactive functionality
- **🎯 Bootstrap 5** - UI framework
- **📊 Chart.js** - Data visualization
- **🎪 Font Awesome** - Icons

### APIs & Services

- **🎧 Spotify Web API** - Music data and user authentication
- **🧠 OpenAI API** - AI chat functionality

### Development Tools

- **📦 Poetry** - Dependency management
- **⚫ Black** - Code formatting
- **🔍 Ruff** - Linting
- **🔧 MyPy** - Type checking
- **✅ Pre-commit hooks** - Code quality enforcement

## 📊 Core Functionality

### 🎛️ Dashboard Analytics

- Total listening time and track counts
- Top artists, albums, and tracks with podium-style visualization
- Genre distribution analysis
- Listening patterns by hour, day, and time periods
- Recently played tracks with real-time updates

### 📈 Detailed Statistics Pages

- **🎤 Artist Stats**: Discography coverage, genre distribution, discovery timeline
- **💿 Album Stats**: Track completion rates, listening patterns
- **🎵 Track Stats**: Play frequency, duration analysis, audio features
- **🎼 Genre Stats**: Musical taste evolution and recommendations

### 🔍 Music Discovery & Search

- **🎵 Universal Search**: Find tracks, artists, albums, and playlists across Spotify's catalog
- **📊 Detailed Track Info**: Audio features, popularity metrics, and release information
- **🎤 Artist Profiles**: Complete discography, top tracks, and related artists
- **💿 Album Deep Dives**: Track listings, release dates, and popularity analysis

### 🎯 Personalized Features

- **🤖 Smart Recommendations**: AI-powered music suggestions based on listening history and preferences
- **🆕 New Releases Hub**: Curated feed of latest releases from followed artists and personalized discoveries
- **📈 Release Tracking**: Monitor upcoming albums and get notified about new music
- **🎪 Recommendation Tuning**: Adjust recommendation parameters based on mood, energy, and genre preferences

### 📊 Data Visualization

- Line charts for listening trends over time
- Polar area charts for hourly distribution
- Doughnut charts for genre breakdowns
- Radar charts for audio feature analysis
- Bar charts for play count comparisons
- Bubble charts for multi-dimensional data

### 🤖 AI Integration

- Natural language chat interface powered by OpenAI
- Context-aware responses based on personal listening data
- Music recommendations and insights

## 🏗️ Architecture Highlights

### ⚡ Asynchronous Processing

- Non-blocking Spotify API calls using `aiohttp`
- Background data synchronization with Celery workers
- Efficient database queries with proper indexing

### 🚀 Caching Strategy

- Redis-based caching for expensive calculations
- Page-level caching for improved performance
- Session management and rate limiting

### 🗄️ Data Models

- Normalized database schema for music data
- Efficient querying with proper indexes
- Time-series data handling for listening history

### 🔒 Security & Authentication

- OAuth 2.0 integration with Spotify
- Secure token management and refresh
- User session handling

## 📸 Screenshots

### 🎛️ Dashboard Overview

![Dashboard Screenshot 1](screenshots/dashboard-1.png)
![Dashboard Screenshot 2](screenshots/dashboard-2.png)
![Dashboard Screenshot 3](screenshots/dashboard-3.png)

### 🎤 Artist Page

![Artist Screenshot 1](screenshots/artist-1.png)
![Artist Screenshot 2](screenshots/artist-2.png)
![Artist Screenshot 3](screenshots/artist-3.png)
![Artist Screenshot 4](screenshots/artist-4.png)
![Artist Screenshot 5](screenshots/artist-5.png)

### 🎵 Track Page

![Track Screenshot 1](screenshots/song-1.png)
![Track Screenshot 2](screenshots/song-2.png)
![Track Screenshot 3](screenshots/song-3.png)

### 🎼 Album Page

![Album Screenshot 1](screenshots/album-1.png)
![Album Screenshot 2](screenshots/album-2.png)
![Album Screenshot 3](screenshots/album-3.png)

### 💬 AI Chat Assistant

![AI Screenshot 1](screenshots/chat-bot.png)

### 🎤 Artist, Album, Track, Genre Stats Page

![Stats Screenshot 1](screenshots/artist-stats-1.png)
![Stats Screenshot 2](screenshots/artist-stats-2.png)
![Stats Screenshot 3](screenshots/artist-stats-3.png)
![Stats Screenshot 4](screenshots/artist-stats-4.png)

### 🔍 Music Search & Discovery

![Search Screenshot 1](screenshots/search-1.png)
![Search Screenshot 2](screenshots/search-2.png)
![Search Screenshot 3](screenshots/search-3.png)
![Search Screenshot 4](screenshots/search-4.png)

### 🆕 New Releases Hub

![New Releases Screenshot 1](screenshots/new-releases.png)

---

**💼 Note**: This project demonstrates full-stack development skills, API integration, real-time data processing, and modern web application architecture. It showcases proficiency in Python, Django, JavaScript, database design, and third-party service integration.
