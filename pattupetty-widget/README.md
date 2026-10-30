# Pattupetty

A small installable web app (PWA) for endless Malayalam Christian songs from YouTube.
It uses the official YouTube IFrame player, so ads and the visible player stay as YouTube
provides them. There is no ad skipping, no audio extraction and no background-play hack.

## Features
- Mood buttons that start an endless queue (search pages are fetched as the queue runs out).
- Library tab: sign in with Google to play your own playlists and liked videos.
- Search tab: English or Malayalam text.
- Link tab: paste any video or playlist link. Works without signing in.
- Sleep timer, small pop-out window (`?mini=1`), installable to the home screen.

## Setup (only needed for Library and Search)
1. Create a project at console.cloud.google.com and enable **YouTube Data API v3**.
2. OAuth consent screen: External, add your Gmail as a Test user.
3. Credentials -> OAuth client ID -> Web application. Add your site origin
   (for local use `http://localhost:8000`).
4. Open the app, tap the gear icon and paste the Client ID. It is stored only in your browser.

## Run locally
    python3 -m http.server 8000

Then open http://localhost:8000. To use it on a phone, host the folder on any HTTPS static
host (GitHub Pages, Azure Static Web Apps) and add that origin to the OAuth client.

## Add to the phone home screen
- Android Chrome: menu -> Install app.
- iPhone Safari: Share -> Add to Home Screen.

This gives an app-style icon that opens full screen. Home-screen widgets in the iOS/Android
sense need a native app and are not possible from a web app.

## Limits
- Playback pauses when the phone locks or the app is backgrounded (YouTube embed rules).
  YouTube Premium is the supported way to get background and lock-screen play.
- While the Google app is in testing mode, sign-ins expire after 7 days.
