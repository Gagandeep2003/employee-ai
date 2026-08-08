import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChatCircleDots, ShieldCheck, Rocket, Users, CheckCircle, ArrowRight, Sparkles, Robot, ChartBar, Globe } from '@phosphor-icons/react';

const LandingPage = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center">
                <ChatCircleDots size={20} weight="fill" className="text-white" />
              </div>
              <span className="text-xl font-bold text-gray-900">Roviq Ai</span>
            </div>

            {/* Desktop Menu */}
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-gray-600 hover:text-gray-900 transition-colors">Features</a>
              <a href="#pricing" className="text-gray-600 hover:text-gray-900 transition-colors">Pricing</a>
              <a href="#use-cases" className="text-gray-600 hover:text-gray-900 transition-colors">Use Cases</a>
              <Link to="/login" className="text-gray-600 hover:text-gray-900 transition-colors">Login</Link>
              <Link to="/register" className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-lg font-medium transition duration-200">
                Get Started Free
              </Link>
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden p-2 text-gray-600 hover:text-gray-900"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileMenuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>

          {/* Mobile Menu */}
          {mobileMenuOpen && (
            <div className="md:hidden py-4 border-t border-gray-100">
              <div className="flex flex-col gap-4">
                <a href="#features" className="text-gray-600 hover:text-gray-900">Features</a>
                <a href="#pricing" className="text-gray-600 hover:text-gray-900">Pricing</a>
                <a href="#use-cases" className="text-gray-600 hover:text-gray-900">Use Cases</a>
                <Link to="/login" className="text-gray-600 hover:text-gray-900">Login</Link>
                <Link to="/register" className="bg-blue-600 text-white px-5 py-2.5 rounded-lg font-medium text-center">
                  Get Started Free
                </Link>
              </div>
            </div>
          )}
        </div>
      </nav>

      {/* Hero Section */}
      <section className="bg-gradient-to-br from-blue-50 via-white to-indigo-50 py-20 lg:py-32">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div>
              <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-sm font-medium mb-6">
                <Sparkles size={16} weight="fill" />
                AI-Powered Customer Engagement
              </div>
              <h1 className="text-4xl lg:text-5xl xl:text-6xl font-bold text-gray-900 leading-tight mb-6">
                Smart Chatbots That Actually Help Your Customers
              </h1>
              <p className="text-xl text-gray-600 mb-8 leading-relaxed">
                Deploy intelligent AI assistants that understand your business, answer questions accurately, 
                and seamlessly connect customers with humans when needed. No coding required.
              </p>
              <div className="flex flex-col sm:flex-row gap-4">
                <Link
                  to="/register"
                  className="inline-flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-8 py-4 rounded-xl font-semibold text-lg transition duration-200 shadow-lg shadow-blue-600/30"
                >
                  Start Free Trial <ArrowRight size={20} />
                </Link>
                <a
                  href="#how-it-works"
                  className="inline-flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-gray-700 px-8 py-4 rounded-xl font-semibold text-lg transition duration-200 border border-gray-200"
                >
                  See How It Works
                </a>
              </div>
              <div className="mt-8 flex items-center gap-6 text-sm text-gray-600">
                <div className="flex items-center gap-2">
                  <CheckCircle size={18} weight="fill" className="text-green-500" />
                  No credit card required
                </div>
                <div className="flex items-center gap-2">
                  <CheckCircle size={18} weight="fill" className="text-green-500" />
                  14-day free trial
                </div>
              </div>
            </div>
            <div className="relative">
              <div className="bg-white rounded-2xl shadow-2xl p-6 border border-gray-100">
                <div className="flex items-center gap-3 mb-4 pb-4 border-b border-gray-100">
                  <div className="w-10 h-10 bg-gradient-to-br from-blue-600 to-indigo-600 rounded-full flex items-center justify-center">
                    <Robot size={20} weight="fill" className="text-white" />
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900">AI Assistant</div>
                    <div className="text-xs text-green-600 flex items-center gap-1">
                      <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                      Online
                    </div>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="bg-gray-100 rounded-lg p-3 max-w-[80%]">
                    <p className="text-sm text-gray-700">Hi! How can I help you today?</p>
                  </div>
                  <div className="bg-blue-600 rounded-lg p-3 max-w-[80%] ml-auto">
                    <p className="text-sm text-white">What are your pricing plans?</p>
                  </div>
                  <div className="bg-gray-100 rounded-lg p-3 max-w-[80%]">
                    <p className="text-sm text-gray-700">We offer flexible plans starting from free tier for small businesses. Would you like me to show you the details?</p>
                  </div>
                </div>
                <div className="mt-4 pt-4 border-t border-gray-100">
                  <div className="bg-gray-50 rounded-lg px-4 py-3 text-sm text-gray-500">
                    Type your message...
                  </div>
                </div>
              </div>
              {/* Decorative elements */}
              <div className="absolute -top-4 -right-4 w-24 h-24 bg-yellow-400/20 rounded-full blur-xl"></div>
              <div className="absolute -bottom-4 -left-4 w-32 h-32 bg-blue-400/20 rounded-full blur-xl"></div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 lg:py-32 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Everything You Need to Engage Customers
            </h2>
            <p className="text-xl text-gray-600">
              Powerful features designed to help businesses of all sizes provide exceptional customer support.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                icon: <ChatCircleDots size={32} weight="fill" className="text-blue-600" />,
                title: "AI-Powered Chat",
                description: "Intelligent chatbots trained on your business data to answer questions accurately 24/7."
              },
              {
                icon: <ShieldCheck size={32} weight="fill" className="text-green-600" />,
                title: "Secure & Private",
                description: "Enterprise-grade security with encrypted conversations and compliance-ready infrastructure."
              },
              {
                icon: <Rocket size={32} weight="fill" className="text-purple-600" />,
                title: "Quick Setup",
                description: "Get started in minutes. No coding required. Just connect your data and customize your widget."
              },
              {
                icon: <Users size={32} weight="fill" className="text-orange-600" />,
                title: "Human Handoff",
                description: "Seamlessly transfer complex queries to your team when the AI needs assistance."
              },
              {
                icon: <ChartBar size={32} weight="fill" className="text-pink-600" />,
                title: "Analytics Dashboard",
                description: "Track conversations, measure performance, and gain insights into customer behavior."
              },
              {
                icon: <Globe size={32} weight="fill" className="text-cyan-600" />,
                title: "Multi-Channel",
                description: "Deploy on your website, mobile app, or integrate with popular messaging platforms."
              }
            ].map((feature, index) => (
              <div key={index} className="group p-8 rounded-2xl border border-gray-100 hover:border-blue-200 hover:shadow-xl transition-all duration-300">
                <div className="w-14 h-14 bg-gray-50 rounded-xl flex items-center justify-center mb-6 group-hover:bg-blue-50 transition-colors">
                  {feature.icon}
                </div>
                <h3 className="text-xl font-semibold text-gray-900 mb-3">{feature.title}</h3>
                <p className="text-gray-600 leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section id="use-cases" className="py-20 lg:py-32 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Built for Real Business Needs
            </h2>
            <p className="text-xl text-gray-600">
              From startups to enterprises, our platform adapts to your specific requirements.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                title: "E-commerce Support",
                description: "Answer product questions, track orders, and reduce cart abandonment with instant responses.",
                businesses: "Online stores, marketplaces"
              },
              {
                title: "SaaS Customer Success",
                description: "Onboard users, troubleshoot issues, and reduce support ticket volume automatically.",
                businesses: "Software companies, platforms"
              },
              {
                title: "Healthcare Booking",
                description: "Schedule appointments, answer FAQs, and provide 24/7 patient communication.",
                businesses: "Clinics, hospitals, practices"
              },
              {
                title: "Education Engagement",
                description: "Support students with admissions queries, course information, and campus services.",
                businesses: "Schools, universities, edtech"
              },
              {
                title: "Financial Services",
                description: "Handle account inquiries, explain products, and guide customers through processes securely.",
                businesses: "Banks, fintech, insurance"
              },
              {
                title: "Hospitality Concierge",
                description: "Assist guests with bookings, amenities, local recommendations, and special requests.",
                businesses: "Hotels, restaurants, travel"
              }
            ].map((useCase, index) => (
              <div key={index} className="bg-white p-8 rounded-2xl shadow-sm hover:shadow-md transition-shadow">
                <h3 className="text-xl font-semibold text-gray-900 mb-3">{useCase.title}</h3>
                <p className="text-gray-600 mb-4">{useCase.description}</p>
                <div className="text-sm text-blue-600 font-medium">{useCase.businesses}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 lg:py-32 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
              Simple, Transparent Pricing
            </h2>
            <p className="text-xl text-gray-600">
              Start free and scale as you grow. No hidden fees, no surprises.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
            {[
              {
                name: "Starter",
                price: "$0",
                period: "/month",
                description: "Perfect for trying out the platform",
                features: [
                  "Up to 100 conversations/month",
                  "Basic AI responses",
                  "Standard widget customization",
                  "Email support",
                  "1 team member"
                ],
                cta: "Get Started Free",
                highlighted: false
              },
              {
                name: "Professional",
                price: "$49",
                period: "/month",
                description: "For growing businesses",
                features: [
                  "Up to 2,000 conversations/month",
                  "Advanced AI training",
                  "Custom branding",
                  "Human handoff",
                  "Analytics dashboard",
                  "Priority support",
                  "5 team members"
                ],
                cta: "Start Free Trial",
                highlighted: true
              },
              {
                name: "Business",
                price: "$149",
                period: "/month",
                description: "For established teams",
                features: [
                  "Unlimited conversations",
                  "Premium AI models",
                  "White-label option",
                  "Advanced analytics",
                  "API access",
                  "Dedicated support",
                  "Unlimited team members",
                  "SLA guarantee"
                ],
                cta: "Contact Sales",
                highlighted: false
              }
            ].map((plan, index) => (
              <div
                key={index}
                className={`relative p-8 rounded-2xl border ${
                  plan.highlighted
                    ? 'border-blue-600 shadow-xl scale-105'
                    : 'border-gray-200 hover:border-blue-200 hover:shadow-lg'
                } transition-all duration-300`}
              >
                {plan.highlighted && (
                  <div className="absolute -top-4 left-1/2 transform -translate-x-1/2 bg-blue-600 text-white px-4 py-1 rounded-full text-sm font-medium">
                    Most Popular
                  </div>
                )}
                <div className="mb-6">
                  <h3 className="text-2xl font-bold text-gray-900 mb-2">{plan.name}</h3>
                  <p className="text-gray-600 text-sm mb-4">{plan.description}</p>
                  <div className="flex items-baseline">
                    <span className="text-4xl font-bold text-gray-900">{plan.price}</span>
                    <span className="text-gray-600 ml-1">{plan.period}</span>
                  </div>
                </div>
                <ul className="space-y-4 mb-8">
                  {plan.features.map((feature, fIndex) => (
                    <li key={fIndex} className="flex items-start gap-3">
                      <CheckCircle size={20} weight="fill" className="text-green-500 mt-0.5 flex-shrink-0" />
                      <span className="text-gray-700">{feature}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  to="/register"
                  className={`block w-full py-3 px-6 rounded-xl font-semibold text-center transition duration-200 ${
                    plan.highlighted
                      ? 'bg-blue-600 hover:bg-blue-700 text-white'
                      : 'bg-gray-100 hover:bg-gray-200 text-gray-900'
                  }`}
                >
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 lg:py-32 bg-gradient-to-br from-blue-600 to-indigo-600">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl lg:text-4xl font-bold text-white mb-6">
            Ready to Transform Your Customer Support?
          </h2>
          <p className="text-xl text-blue-100 mb-10 leading-relaxed">
            Join thousands of businesses providing faster, smarter customer service with AI-powered chatbots.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/register"
              className="inline-flex items-center justify-center gap-2 bg-white hover:bg-gray-50 text-blue-600 px-8 py-4 rounded-xl font-semibold text-lg transition duration-200"
            >
              Start Your Free Trial
            </Link>
            <a
              href="#contact"
              className="inline-flex items-center justify-center gap-2 bg-transparent hover:bg-white/10 text-white px-8 py-4 rounded-xl font-semibold text-lg transition duration-200 border border-white/30"
            >
              Talk to Sales
            </a>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-900 text-gray-400 py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid md:grid-cols-4 gap-12">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-500 rounded-lg flex items-center justify-center">
                  <ChatCircleDots size={20} weight="fill" className="text-white" />
                </div>
                <span className="text-xl font-bold text-white">Roviq Ai</span>
              </div>
              <p className="text-sm leading-relaxed">
                Intelligent chatbots that help businesses engage customers 24/7 with accuracy and care.
              </p>
            </div>
            <div>
              <h4 className="text-white font-semibold mb-4">Product</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#features" className="hover:text-white transition-colors">Features</a></li>
                <li><a href="#pricing" className="hover:text-white transition-colors">Pricing</a></li>
                <li><a href="#use-cases" className="hover:text-white transition-colors">Use Cases</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Documentation</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-white font-semibold mb-4">Company</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="hover:text-white transition-colors">About</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Blog</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Careers</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Contact</a></li>
              </ul>
            </div>
            <div>
              <h4 className="text-white font-semibold mb-4">Legal</h4>
              <ul className="space-y-2 text-sm">
                <li><a href="#" className="hover:text-white transition-colors">Privacy Policy</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Terms of Service</a></li>
                <li><a href="#" className="hover:text-white transition-colors">Security</a></li>
              </ul>
            </div>
          </div>
          <div className="mt-12 pt-8 border-t border-gray-800 text-sm text-center">
            <p>&copy; {new Date().getFullYear()} Roviq Ai. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
