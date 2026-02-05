# Phisherman AI - Landing Page

A modern, responsive landing page for the AI-Resistant Phishing Detection & Deception Framework built with Next.js, TypeScript, and Tailwind CSS.

## 🚀 Features

- **Modern Tech Stack**: Next.js 14 with App Router, TypeScript, Tailwind CSS
- **Smooth Animations**: Framer Motion for scroll animations, GSAP for micro-interactions
- **Responsive Design**: Mobile-first approach with tablet and desktop layouts
- **Accessibility**: Semantic HTML, proper ARIA labels, keyboard navigation
- **Component Library**: Built with shadcn/ui components for consistency
- **Custom Color Palette**: Deep midnight blue theme with electric cyan accents

## 🎨 Design System

### Color Palette

- **Primary Background**: Deep Midnight Blue (`#0A192F`)
- **Accent/Action**: Electric Cyan (`#4ADE80`)
- **Text**: Off-White/Light Gray (`#E0E7FF`)
- **Warning/Danger**: Sunset Orange (`#F59E0B`)

### Typography

- Clean, modern font stack with excellent readability
- Proper contrast ratios for accessibility
- Responsive text sizing

## 🛠️ Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Animations**: Framer Motion + GSAP
- **Components**: shadcn/ui
- **Icons**: Lucide React

## 📦 Installation

### Prerequisites

- Node.js 18+
- npm, yarn, or pnpm

### Setup

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd phisherman-ai-landing
   ```

2. **Install dependencies**

   ```bash
   npm install
   # or
   yarn install
   # or
   pnpm install
   ```

3. **Run the development server**

   ```bash
   npm run dev
   # or
   yarn dev
   # or
   pnpm dev
   ```

4. **Open your browser**
   Navigate to [http://localhost:3000](http://localhost:3000)

## 🏗️ Project Structure

```
├── app/
│   ├── globals.css          # Global styles and Tailwind imports
│   ├── layout.tsx           # Root layout component
│   └── page.tsx             # Main landing page
├── components/
│   ├── ui/                  # shadcn/ui components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   └── badge.tsx
│   ├── Header.tsx           # Navigation header
│   ├── Hero.tsx             # Hero section with animations
│   ├── Features.tsx         # Key features cards
│   ├── HowItWorks.tsx       # 3-step process flow
│   ├── DemoCard.tsx         # Interactive demo component
│   ├── WhyItMatters.tsx     # Benefits and stats
│   └── Footer.tsx           # Footer with links
├── lib/
│   └── utils.ts             # Utility functions
├── tailwind.config.js       # Tailwind configuration
├── tsconfig.json            # TypeScript configuration
└── package.json             # Dependencies and scripts
```

## 🎯 Key Components

### Header

- Fixed navigation with logo and CTAs
- Mobile-responsive hamburger menu
- Smooth backdrop blur effect

### Hero Section

- Animated shield and neural wave graphics
- GSAP micro-interactions
- Call-to-action buttons with hover effects

### Features

- Three feature cards with icons
- Scroll-triggered animations
- Hover effects and transitions

### How It Works

- Three-step process visualization
- Desktop horizontal flow, mobile vertical
- Animated arrows and icons

### Demo Card

- Interactive phishing detection demo
- Mock analysis with progress bars
- Report generation simulation

### Why It Matters

- Benefit points with icons
- Statistics section
- Scroll animations

### Footer

- Company information and links
- Contact CTAs
- Copyright and legal links

## 🎨 Customization

### Colors

Update the color palette in `tailwind.config.js`:

```javascript
colors: {
  'midnight-blue': '#0A192F',
  'electric-cyan': '#4ADE80',
  'off-white': '#E0E7FF',
  'sunset-orange': '#F59E0B',
}
```

### Animations

- **Framer Motion**: Used for scroll-triggered animations and page transitions
- **GSAP**: Used sparingly for hero micro-interactions (neural wave bounce)

### Content

All content is defined in the respective component files. Update the text, links, and CTAs as needed.

## 📱 Responsive Design

- **Mobile First**: Designed for mobile devices first
- **Breakpoints**:
  - Mobile: < 768px
  - Tablet: 768px - 1024px
  - Desktop: > 1024px
- **Navigation**: Collapsible hamburger menu on mobile
- **Layout**: Responsive grid systems and flexible components

## ♿ Accessibility

- **Semantic HTML**: Proper use of headings, sections, and landmarks
- **ARIA Labels**: Screen reader friendly navigation and buttons
- **Keyboard Navigation**: Full keyboard accessibility
- **Color Contrast**: WCAG compliant contrast ratios
- **Focus States**: Visible focus indicators

## 🚀 Deployment

### Build for Production

```bash
npm run build
```

### Start Production Server

```bash
npm start
```

### Deploy to Vercel

```bash
npx vercel
```

## 📝 Notes

- **Demo Features**: The demo card shows mock data and simulated interactions
- **Animations**: Optimized for performance with proper cleanup
- **SEO**: Basic meta tags included, expand as needed
- **Performance**: Images optimized, lazy loading implemented

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

---

**Phisherman AI** - Advanced AI-resistant phishing detection and deception framework.
