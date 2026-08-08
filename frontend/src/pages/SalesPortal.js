import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

const SalesPortal = () => {
  const [businesses, setBusinesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [formData, setFormData] = useState({
    companyName: '',
    contactPerson: '',
    email: '',
    phone: '',
    industry: '',
    notes: '',
  });
  const [stats, setStats] = useState({
    totalReferrals: 0,
    activeSubscriptions: 0,
    totalCommission: 0,
    pendingCommission: 0,
  });

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const token = localStorage.getItem('token');
      const [businessesRes, statsRes] = await Promise.all([
        axios.get(`${process.env.REACT_APP_API_URL}/sales/referrals`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        axios.get(`${process.env.REACT_APP_API_URL}/sales/stats`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      setBusinesses(businessesRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${process.env.REACT_APP_API_URL}/sales/referrals`,
        formData,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Business added successfully! Temporary password sent to their email.');
      setShowAddModal(false);
      setFormData({
        companyName: '',
        contactPerson: '',
        email: '',
        phone: '',
        industry: '',
        notes: '',
      });
      fetchDashboardData();
    } catch (error) {
      alert(error.response?.data?.message || 'Failed to add business');
    }
  };

  const handleWithdrawCommission = async () => {
    if (!window.confirm('Request commission withdrawal to your registered bank account?')) return;

    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${process.env.REACT_APP_API_URL}/sales/withdraw-commission`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      alert('Withdrawal request submitted! Processing time: 3-5 business days.');
      fetchDashboardData();
    } catch (error) {
      alert(error.response?.data?.message || 'Failed to request withdrawal');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold text-gray-900">Sales Portal Dashboard</h1>
            <button
              onClick={() => setShowAddModal(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition duration-200"
            >
              + Add New Business
            </button>
          </div>
        </div>
      </header>

      {/* Stats Grid */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white p-6 rounded-xl shadow-sm">
            <div className="text-sm font-medium text-gray-600 mb-2">Total Referrals</div>
            <div className="text-3xl font-bold text-gray-900">{stats.totalReferrals}</div>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-sm">
            <div className="text-sm font-medium text-gray-600 mb-2">Active Subscriptions</div>
            <div className="text-3xl font-bold text-green-600">{stats.activeSubscriptions}</div>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-sm">
            <div className="text-sm font-medium text-gray-600 mb-2">Total Commission Earned</div>
            <div className="text-3xl font-bold text-blue-600">${stats.totalCommission.toFixed(2)}</div>
          </div>
          <div className="bg-white p-6 rounded-xl shadow-sm">
            <div className="text-sm font-medium text-gray-600 mb-2">Available for Withdrawal</div>
            <div className="text-3xl font-bold text-green-600">${stats.pendingCommission.toFixed(2)}</div>
            <button
              onClick={handleWithdrawCommission}
              disabled={stats.pendingCommission === 0}
              className="mt-2 text-sm text-blue-600 hover:text-blue-800 disabled:opacity-50"
            >
              Withdraw →
            </button>
          </div>
        </div>

        {/* Commission Info */}
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-6 mb-8">
          <h3 className="text-lg font-semibold text-blue-900 mb-2">💰 Commission Structure</h3>
          <p className="text-blue-800">
            You earn <strong>15% recurring commission</strong> on every paid plan purchased by businesses you refer.
            Commission continues as long as the business maintains an active paid subscription.
          </p>
        </div>

        {/* Businesses Table */}
        <div className="bg-white rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">Referred Businesses</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Company
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Contact
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Plan
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Commission
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Joined
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {businesses.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="px-6 py-8 text-center text-gray-500">
                      No businesses referred yet. Start adding businesses to earn commission!
                    </td>
                  </tr>
                ) : (
                  businesses.map((biz) => (
                    <tr key={biz.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">{biz.companyName}</div>
                        <div className="text-sm text-gray-500">{biz.industry}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{biz.contactPerson}</div>
                        <div className="text-sm text-gray-500">{biz.email}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                            biz.status === 'active'
                              ? 'bg-green-100 text-green-800'
                              : biz.status === 'pending'
                              ? 'bg-yellow-100 text-yellow-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {biz.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                            biz.plan === 'paid'
                              ? 'bg-blue-100 text-blue-800'
                              : 'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {biz.plan || 'Free'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">
                          ${biz.commissionEarned?.toFixed(2) || '0.00'}
                        </div>
                        <div className="text-xs text-gray-500">
                          {biz.commissionRate || 15}% rate
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {new Date(biz.createdAt).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Add Business Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-lg w-full p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-gray-900">Add New Business</h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Company Name</label>
                <input
                  type="text"
                  required
                  value={formData.companyName}
                  onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Contact Person</label>
                <input
                  type="text"
                  required
                  value={formData.contactPerson}
                  onChange={(e) => setFormData({ ...formData, contactPerson: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Industry</label>
                <select
                  value={formData.industry}
                  onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select Industry</option>
                  <option value="retail">Retail</option>
                  <option value="healthcare">Healthcare</option>
                  <option value="education">Education</option>
                  <option value="technology">Technology</option>
                  <option value="hospitality">Hospitality</option>
                  <option value="finance">Finance</option>
                  <option value="other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                <textarea
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  rows="3"
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Add Business
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default SalesPortal;
