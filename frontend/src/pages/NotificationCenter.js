import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

const NotificationCenter = () => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all, unread, announcements, system

  useEffect(() => {
    fetchNotifications();
  }, []);

  const fetchNotifications = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(
        `${process.env.REACT_APP_API_URL}/notifications`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(response.data);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const markAsRead = async (id) => {
    try {
      const token = localStorage.getItem('token');
      await axios.put(
        `${process.env.REACT_APP_API_URL}/notifications/${id}/read`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(notifications.map(n => 
        n.id === id ? { ...n, read: true } : n
      ));
    } catch (error) {
      console.error('Failed to mark as read:', error);
    }
  };

  const markAllAsRead = async () => {
    try {
      const token = localStorage.getItem('token');
      await axios.put(
        `${process.env.REACT_APP_API_URL}/notifications/read-all`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(notifications.map(n => ({ ...n, read: true })));
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const deleteNotification = async (id) => {
    if (!window.confirm('Delete this notification?')) return;
    try {
      const token = localStorage.getItem('token');
      await axios.delete(
        `${process.env.REACT_APP_API_URL}/notifications/${id}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setNotifications(notifications.filter(n => n.id !== id));
    } catch (error) {
      console.error('Failed to delete notification:', error);
    }
  };

  const filteredNotifications = notifications.filter(n => {
    if (filter === 'unread') return !n.read;
    if (filter === 'announcements') return n.type === 'announcement';
    if (filter === 'system') return n.type === 'system';
    return true;
  });

  const unreadCount = notifications.filter(n => !n.read).length;

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
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
              <p className="text-gray-600 mt-1">
                {unreadCount > 0 ? `${unreadCount} unread message(s)` : 'All caught up!'}
              </p>
            </div>
            {unreadCount > 0 && (
              <button
                onClick={markAllAsRead}
                className="text-blue-600 hover:text-blue-800 font-medium"
              >
                Mark all as read
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Filters */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex gap-2 overflow-x-auto">
          {['all', 'unread', 'announcements', 'system'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-lg font-medium whitespace-nowrap transition duration-200 ${
                filter === f
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-700 hover:bg-gray-100'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
              {f === 'unread' && unreadCount > 0 && (
                <span className="ml-2 bg-red-500 text-white text-xs px-2 py-0.5 rounded-full">
                  {unreadCount}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Notifications List */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        {filteredNotifications.length === 0 ? (
          <div className="bg-white rounded-xl shadow-sm p-12 text-center">
            <div className="text-6xl mb-4">🔔</div>
            <h3 className="text-xl font-semibold text-gray-900 mb-2">No notifications</h3>
            <p className="text-gray-600">
              {filter === 'all'
                ? "You don't have any notifications yet."
                : `No ${filter} notifications.`}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredNotifications.map((notification) => (
              <div
                key={notification.id}
                className={`bg-white rounded-xl shadow-sm p-6 transition duration-200 ${
                  !notification.read ? 'border-l-4 border-blue-500' : ''
                }`}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span
                        className={`px-3 py-1 text-xs font-semibold rounded-full ${
                          notification.type === 'announcement'
                            ? 'bg-purple-100 text-purple-800'
                            : notification.type === 'system'
                            ? 'bg-blue-100 text-blue-800'
                            : notification.type === 'alert'
                            ? 'bg-red-100 text-red-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {notification.type}
                      </span>
                      {!notification.read && (
                        <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
                          New
                        </span>
                      )}
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">
                      {notification.title}
                    </h3>
                    <p className="text-gray-600 mb-3">{notification.message}</p>
                    <div className="text-sm text-gray-500">
                      {new Date(notification.createdAt).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex gap-2 ml-4">
                    {!notification.read && (
                      <button
                        onClick={() => markAsRead(notification.id)}
                        className="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-lg"
                      >
                        Mark as read
                      </button>
                    )}
                    <button
                      onClick={() => deleteNotification(notification.id)}
                      className="px-3 py-1 text-sm text-red-600 hover:bg-red-50 rounded-lg"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Back to Dashboard Link */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Link
          to="/owner/dashboard"
          className="text-blue-600 hover:text-blue-800 font-medium"
        >
          ← Back to Dashboard
        </Link>
      </div>
    </div>
  );
};

export default NotificationCenter;
