import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';

const SalesLogin = () => {
  const [email, setEmail] = useState('');
  const [tempPassword, setTempPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [step, setStep] = useState(1); // 1: Login, 2: Change Password
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await axios.post(`${process.env.REACT_APP_API_URL}/auth/login`, {
        email,
        password: tempPassword,
      });

      if (response.data.user.role === 'sales') {
        // Check if this is a temporary password login
        if (response.data.user.isTemporaryPassword) {
          setStep(2);
        } else {
          localStorage.setItem('token', response.data.token);
          navigate('/sales/dashboard');
        }
      } else {
        setError('Access denied. Sales portal access required.');
      }
    } catch (err) {
      setError(err.response?.data?.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match');
      setLoading(false);
      return;
    }

    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters');
      setLoading(false);
      return;
    }

    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${process.env.REACT_APP_API_URL}/auth/change-password`,
        { currentPassword: tempPassword, newPassword },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      alert('Password changed successfully! Please login with your new password.');
      setStep(1);
      setTempPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to change password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-8">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Sales Portal</h1>
          <p className="text-gray-600 mt-2">
            {step === 1 ? 'Login with your temporary password' : 'Set your permanent password'}
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 text-red-700 rounded-lg">
            {error}
          </div>
        )}

        {step === 1 ? (
          <form onSubmit={handleLogin} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="sales@company.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Temporary Password</label>
              <input
                type="password"
                value={tempPassword}
                onChange={(e) => setTempPassword(e.target.value)}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter temporary password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition duration-200 disabled:opacity-50"
            >
              {loading ? 'Logging in...' : 'Login'}
            </button>

            <p className="text-center text-sm text-gray-600">
              Contact your admin for temporary password access
            </p>
          </form>
        ) : (
          <form onSubmit={handleChangePassword} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Enter new password"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Confirm Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="Confirm new password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg transition duration-200 disabled:opacity-50"
            >
              {loading ? 'Changing Password...' : 'Set New Password'}
            </button>
          </form>
        )}

        <div className="mt-6 text-center">
          <Link to="/" className="text-blue-600 hover:text-blue-800 text-sm">
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
};

export default SalesLogin;
