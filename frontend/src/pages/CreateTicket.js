import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';

const CreateTicket = () => {
  const [formData, setFormData] = useState({
    subject: '',
    category: 'technical',
    priority: 'medium',
    description: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${process.env.REACT_APP_API_URL}/tickets`,
        formData,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Ticket created successfully! Our support team will respond soon.');
      navigate('/owner/dashboard');
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to create ticket. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <h1 className="text-2xl font-bold text-gray-900">Create Support Ticket</h1>
          <p className="text-gray-600 mt-1">Describe your issue and we'll help you resolve it.</p>
        </div>
      </header>

      {/* Form */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-sm p-8">
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
              {error}
            </div>
          )}

          <div className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Subject</label>
              <input
                type="text"
                value={formData.subject}
                onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Brief summary of your issue"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Category</label>
                <select
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="technical">Technical Issue</option>
                  <option value="billing">Billing & Payments</option>
                  <option value="feature">Feature Request</option>
                  <option value="account">Account Access</option>
                  <option value="integration">Integration Help</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Priority</label>
                <select
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="low">Low - General question</option>
                  <option value="medium">Medium - Normal issue</option>
                  <option value="high">High - Important problem</option>
                  <option value="urgent">Urgent - Service down</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
                rows="6"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Please provide detailed information about your issue, including steps to reproduce, expected behavior, and any relevant screenshots or error messages."
              />
              <p className="text-xs text-gray-500 mt-1">
                The more details you provide, the faster we can help resolve your issue.
              </p>
            </div>

            <div className="flex gap-4 pt-4">
              <button
                type="button"
                onClick={() => navigate('/owner/dashboard')}
                className="flex-1 px-6 py-3 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 font-medium transition duration-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition duration-200 disabled:opacity-50"
              >
                {loading ? 'Creating Ticket...' : 'Submit Ticket'}
              </button>
            </div>
          </div>
        </form>

        {/* Help Info */}
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-2">💡 Need Immediate Help?</h3>
          <p className="text-blue-800 mb-4">
            For urgent issues, you can also reach out via our live chat widget (bottom right corner) 
            or email us directly at support@example.com.
          </p>
          <div className="flex flex-wrap gap-4 text-sm text-blue-800">
            <div className="flex items-center gap-2">
              <span className="font-semibold">Response Times:</span>
            </div>
            <div>🟢 Urgent: &lt; 1 hour</div>
            <div>🟡 High: &lt; 4 hours</div>
            <div>🔵 Medium: &lt; 24 hours</div>
            <div>⚪ Low: &lt; 48 hours</div>
          </div>
        </div>

        {/* Back Link */}
        <div className="mt-6">
          <Link to="/owner/dashboard" className="text-blue-600 hover:text-blue-800 font-medium">
            ← Back to Dashboard
          </Link>
        </div>
      </div>
    </div>
  );
};

export default CreateTicket;
