import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './UserApproval.css';

const UserApproval = () => {
  const [pendingUsers, setPendingUsers] = useState([]);
  const [allUsers, setAllUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('pending');
  const [message, setMessage] = useState('');
  const navigate = useNavigate();

  const fetchPendingUsers = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      if (!token) {
        alert('No token found, please log in.');
        navigate('/');
        return;
      }

      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/pending-users`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.status === 403) {
        alert('Access denied. Owner role required.');
        navigate('/');
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch pending users');
      }

      const data = await response.json();
      setPendingUsers(data.users);
    } catch (error) {
      setMessage(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchAllUsers = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      if (!token) {
        alert('No token found, please log in.');
        navigate('/');
        return;
      }

      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/all-users`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.status === 403) {
        alert('Access denied. Owner role required.');
        navigate('/');
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to fetch all users');
      }

      const data = await response.json();
      setAllUsers(data.users);
    } catch (error) {
      setMessage(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleUserAction = async (userId, action) => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/update-user-approval`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ userId, action })
      });

      if (!response.ok) {
        throw new Error(`Failed to ${action} user`);
      }

      const data = await response.json();
      setMessage(`Success: ${data.message}`);
      
      // Refresh the lists
      fetchPendingUsers();
      fetchAllUsers();
    } catch (error) {
      setMessage(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPendingUsers();
    fetchAllUsers();
  }, []);

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString();
  };

  const getStatusBadge = (user) => {
    if (!user.is_verified) {
      return <span className="badge badge-warning">Email Not Verified</span>;
    } else if (!user.is_approved) {
      return <span className="badge badge-pending">Pending Approval</span>;
    } else {
      return <span className="badge badge-approved">Approved</span>;
    }
  };

  return (
    <div className="user-approval-container">
      <button className="btn btn-back" onClick={() => navigate('/landing')}>
        ← Back to Landing Page
      </button>

      <div className="header">
        <h1>Approvals</h1>
        <p>Approve or reject user registrations</p>
      </div>

      {message && (
        <div className="message">
          {message}
        </div>
      )}

      <div className="tabs">
        <button 
          className={`tab ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          Pending Approvals ({pendingUsers.length})
        </button>
        <button 
          className={`tab ${activeTab === 'all' ? 'active' : ''}`}
          onClick={() => setActiveTab('all')}
        >
          All Users ({allUsers.length})
        </button>
      </div>

      {loading && (
        <div className="loading">Loading...</div>
      )}

      {!loading && activeTab === 'pending' && (
        <div>
          <h2>Users Pending Approval</h2>
          {pendingUsers.length === 0 ? (
            <div className="empty-state">
              No users pending approval
            </div>
          ) : (
            <table className="users-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Registration Date</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pendingUsers.map(user => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>{user.role}</td>
                    <td>{formatDate(user.createdAt)}</td>
                    <td>{getStatusBadge(user)}</td>
                    <td>
                      <div className="action-buttons">
                        <button 
                          className="btn btn-approve"
                          onClick={() => handleUserAction(user.id, 'approve')}
                          disabled={loading}
                        >
                          Approve
                        </button>
                        <button 
                          className="btn btn-reject"
                          onClick={() => handleUserAction(user.id, 'reject')}
                          disabled={loading}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {!loading && activeTab === 'all' && (
        <div>
          <h2>All Users</h2>
          {allUsers.length === 0 ? (
            <div className="empty-state">
              No users found
            </div>
          ) : (
            <table className="users-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Registration Date</th>
                  <th>Status</th>
                  <th>Approved By</th>
                  <th>Approved Date</th>
                </tr>
              </thead>
              <tbody>
                {allUsers.map(user => (
                  <tr key={user.id}>
                    <td>{user.username}</td>
                    <td>{user.email}</td>
                    <td>{user.role}</td>
                    <td>{formatDate(user.createdAt)}</td>
                    <td>{getStatusBadge(user)}</td>
                    <td>{user.approved_by || '-'}</td>
                    <td>{user.approved_at ? formatDate(user.approved_at) : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};

export default UserApproval;
