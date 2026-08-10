import React, { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { toast } from 'sonner';
import { Users, Building, ChartLine, UserPlus, Copy, CheckCircle } from '@phosphor-icons/react';

export default function AdminDashboard() {
  const [stats, setStats] = useState({ total_users: 0, total_businesses: 0, active_plans: 0 });
  const [loading, setLoading] = useState(true);
  
  // Sales Onboarding State
  const [showSalesForm, setShowSalesForm] = useState(false);
  const [salesData, setSalesData] = useState({ name: '', email: '', company: '' });
  const [generating, setGenerating] = useState(false);
  const [generatedCreds, setGeneratedCreds] = useState(null);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await api.get('/admin/stats');
      setStats(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleOnboardSales = async (e) => {
    e.preventDefault();
    setGenerating(true);
    try {
      // Call the backend endpoint to create sales user & send email
      const res = await api.post('/admin/sales/onboard', salesData);
      setGeneratedCreds(res.data); // Expecting { tempPassword, loginUrl }
      toast.success('Sales agent onboarded! Email sent.');
      setSalesData({ name: '', email: '', company: '' });
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to onboard agent');
    } finally {
      setGenerating(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard');
  };

  if (loading) return <div className="p-8 text-center">Loading admin data...</div>;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      <h1 className="text-3xl font-bold text-gray-900">Admin Overview</h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard title="Total Users" value={stats.total_users} icon={<Users size={32} />} color="bg-blue-500" />
        <StatCard title="Total Businesses" value={stats.total_businesses} icon={<Building size={32} />} color="bg-emerald-500" />
        <StatCard title="Active Paid Plans" value={stats.active_plans} icon={<ChartLine size={32} />} color="bg-purple-500" />
      </div>

      {/* Sales Onboarding Section */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="p-6 border-b border-gray-100 flex justify-between items-center bg-gray-50">
          <div>
            <h2 className="text-xl font-semibold flex items-center gap-2">
              <UserPlus className="text-indigo-600" /> Sales Team Management
            </h2>
            <p className="text-sm text-gray-500 mt-1">Onboard new sales agents to track commissions (15%)</p>
          </div>
          {!showSalesForm && (
            <button 
              onClick={() => setShowSalesForm(true)}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 text-sm font-medium transition-colors"
            >
              + Add Sales Agent
            </button>
          )}
        </div>

        {showSalesForm && (
          <div className="p-6 bg-indigo-50/50 animate-in fade-in slide-in-from-top-2">
            {!generatedCreds ? (
              <form onSubmit={handleOnboardSales} className="space-y-4 max-w-2xl">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                    <input required type="text" className="w-full px-3 py-2 border rounded-md" 
                      value={salesData.name} onChange={e => setSalesData({...salesData, name: e.target.value})} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
                    <input required type="email" className="w-full px-3 py-2 border rounded-md" 
                      value={salesData.email} onChange={e => setSalesData({...salesData, email: e.target.value})} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Company / Agency Name</label>
                    <input required type="text" className="w-full px-3 py-2 border rounded-md" 
                      value={salesData.company} onChange={e => setSalesData({...salesData, company: e.target.value})} />
                  </div>
                </div>
                <div className="flex gap-3 pt-2">
                  <button type="submit" disabled={generating} 
                    className="px-6 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50">
                    {generating ? 'Creating Account...' : 'Generate Account & Send Email'}
                  </button>
                  <button type="button" onClick={() => setShowSalesForm(false)} 
                    className="px-6 py-2 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50">
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div className="bg-white p-6 rounded-lg border border-indigo-200 shadow-sm">
                <div className="flex items-start gap-3 mb-4">
                  <CheckCircle size={24} className="text-green-500 shrink-0" />
                  <div>
                    <h3 className="font-semibold text-gray-900">Sales Agent Created Successfully</h3>
                    <p className="text-sm text-gray-600">An email has been sent to <strong>{generatedCreds.email}</strong> with their temporary password.</p>
                  </div>
                </div>
                
                <div className="bg-gray-50 p-4 rounded-md space-y-3 text-sm">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Login URL:</span>
                    <div className="flex items-center gap-2">
                      <code className="bg-white px-2 py-1 rounded border">{generatedCreds.loginUrl}</code>
                      <button onClick={() => copyToClipboard(generatedCreds.loginUrl)} className="text-indigo-600 hover:underline">Copy</button>
                    </div>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-gray-500">Temporary Password:</span>
                    <div className="flex items-center gap-2">
                      <code className="bg-white px-2 py-1 rounded border font-mono text-red-600">{generatedCreds.tempPassword}</code>
                      <button onClick={() => copyToClipboard(generatedCreds.tempPassword)} className="text-indigo-600 hover:underline">Copy</button>
                    </div>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-4">⚠️ For security, share the temporary password via a separate channel if possible. The user must change this on first login.</p>
                
                <button onClick={() => { setShowSalesForm(false); setGeneratedCreds(null); }} 
                  className="mt-6 text-sm text-indigo-600 hover:underline font-medium">
                  Onboard Another Agent
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent Referrals / Sales Table could go here */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Recent Commission Activity</h3>
        <p className="text-sm text-gray-500">Commission tracking table implementation pending...</p>
      </div>
    </div>
  );
}

function StatCard({ title, value, icon, color }) {
  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200 flex items-center gap-4">
      <div className={`p-4 rounded-full text-white ${color}`}>{icon}</div>
      <div>
        <p className="text-sm text-gray-500 font-medium">{title}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      </div>
    </div>
  );
}
