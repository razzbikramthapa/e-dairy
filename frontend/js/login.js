// login.js - Client authentication logic for e-Dairy with OTP System

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const tabLogin = document.getElementById('tabLogin');
  const tabRegister = document.getElementById('tabRegister');
  const roleBtns = document.querySelectorAll('.role-btn');
  
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const authAlert = document.getElementById('authAlert');
  
  const loginFormTitle = document.getElementById('loginFormTitle');
  const loginFormDesc = document.getElementById('loginFormDesc');
  const registerFormTitle = document.getElementById('registerFormTitle');
  

  const regPhoneInput = document.getElementById('regPhone');
  const regPassInput = document.getElementById('regPass');
  const btnGetCode = document.getElementById('btnGetCode');
  const btnForgotOTP = document.getElementById('btnForgotOTP');

  // API Config
  const API_BASE_URL = window.location.origin + '/api';

  // State Variables
  let currentTab = 'login'; // 'login' or 'register'
  let currentRole = 'farmer'; // 'farmer' or 'agent'
  let lastGeneratedOTP = ''; // Stores generated OTP in memory for simulation/validation
  let targetOTPPhone = ''; // Keeps track of which phone requested the code

  // Alert Helpers
  function showAlert(message, type = 'danger') {
    authAlert.innerHTML = message;
    authAlert.className = `modal-alert ${type}`;
    authAlert.style.display = 'block';
  }

  function clearAlert() {
    authAlert.innerText = '';
    authAlert.className = 'modal-alert';
    authAlert.style.display = 'none';
  }

  // UI Updates based on selected Tab (Login vs Register)
  function switchTab(tab) {
    clearAlert();
    currentTab = tab;
    
    if (tab === 'login') {
      tabLogin.classList.add('active');
      tabRegister.classList.remove('active');
      loginForm.classList.add('active');
      registerForm.classList.remove('active');
    } else {
      tabRegister.classList.add('active');
      tabLogin.classList.remove('active');
      registerForm.classList.add('active');
      loginForm.classList.remove('active');
    }
    
    updateFormLabels();
  }

  // UI Updates based on selected Role (Farmer vs Collection Centre)
  function switchRole(role) {
    clearAlert();
    currentRole = role;
    
    roleBtns.forEach(btn => {
      if (btn.getAttribute('data-role') === role) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Toggle role-specific signup fields with animation
    const farmerFields = document.getElementById('farmerFields');
    const agentFields = document.getElementById('agentFields');
    if (farmerFields && agentFields) {
      if (role === 'farmer') {
        agentFields.style.display = 'none';
        farmerFields.style.display = '';
        // Re-trigger animation
        farmerFields.style.animation = 'none';
        farmerFields.offsetHeight; // reflow
        farmerFields.style.animation = '';
      } else {
        farmerFields.style.display = 'none';
        agentFields.style.display = '';
        // Re-trigger animation
        agentFields.style.animation = 'none';
        agentFields.offsetHeight; // reflow
        agentFields.style.animation = '';
      }
    }

    // Clear all registration and login inputs when switching roles
    const fieldsToClear = [
      'loginUser', 'loginPass', 'regFirst', 'regLast', 
      'regFarmName', 'regCentreName', 'regAddr', 'regPhone', 'regPass'
    ];
    fieldsToClear.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });

    // Reset temporary OTP states
    lastGeneratedOTP = '';
    targetOTPPhone = '';

    updateFormLabels();
  }

  function updateFormLabels() {
    const roleLabel = currentRole === 'farmer' ? 'Farmer' : 'Collection Centre';

    // Always update BOTH forms so switching role on either tab is instant
    loginFormTitle.innerText = `${roleLabel} Sign In`;
    loginFormDesc.innerText = currentRole === 'farmer'
      ? 'Access your milk yield, FAT analysis, and payments ledger'
      : 'Open milk collection agent panel and weigh scales interface';

    registerFormTitle.innerText = `${roleLabel} Registration`;

    const registerFormDesc = document.getElementById('registerFormDesc');
    if (registerFormDesc) {
      registerFormDesc.innerText = currentRole === 'farmer'
        ? 'Create a new farmer account on the e-Dairy network'
        : 'Register your collection centre on the e-Dairy network';
    }
  }

  // Event Listeners for Tabs & Roles
  tabLogin.addEventListener('click', () => switchTab('login'));
  tabRegister.addEventListener('click', () => switchTab('register'));

  roleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const selectedRole = btn.getAttribute('data-role');
      switchRole(selectedRole);
    });
  });

  // Handle "Get Code" Button Click
  btnGetCode.addEventListener('click', async () => {
    clearAlert();
    const phone = regPhoneInput.value.trim();
    
    if (!phone) {
      showAlert('Please enter your mobile phone number first.');
      return;
    }

    btnGetCode.disabled = true;
    btnGetCode.innerText = 'Sending...';

    try {
      const response = await fetch(`${API_BASE_URL}/generate-code/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, purpose: 'register' })
      });
      const data = await response.json();

      if (response.ok) {
        lastGeneratedOTP = data.code || 'sent';
        targetOTPPhone = phone;
        if (data.code) {
          showAlert(`Verification code generated: ${data.code} (Enter this in the OTP input)`, 'success');
        } else {
          showAlert('Verification code sent successfully via SMS.', 'success');
        }
        
        let counter = 15;
        const interval = setInterval(() => {
          counter--;
          if (counter > 0) {
            btnGetCode.innerText = `Resend (${counter}s)`;
          } else {
            clearInterval(interval);
            btnGetCode.innerText = 'Get Code';
            btnGetCode.disabled = false;
          }
        }, 1000);
      } else {
        btnGetCode.disabled = false;
        btnGetCode.innerText = 'Get Code';
        showAlert(data.detail || 'Failed to request verification code.');
      }
    } catch (err) {
      btnGetCode.disabled = false;
      btnGetCode.innerText = 'Get Code';
      showAlert('Failed to connect to verification server.');
    }
  });

  // Handle "Forgot OTP" Button Click on Login Form
  if (btnForgotOTP) {
    btnForgotOTP.addEventListener('click', async () => {
      clearAlert();
      const phone = document.getElementById('loginUser').value.trim();
      
      if (!phone) {
        showAlert('Please enter your mobile number first.');
        return;
      }

      btnForgotOTP.disabled = true;
      btnForgotOTP.innerText = 'Sending OTP...';

      try {
        const response = await fetch(`${API_BASE_URL}/generate-code/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone, purpose: 'login' })
        });
        const data = await response.json();

        if (response.ok) {
          if (data.code) {
            showAlert(`Verification code generated: ${data.code} (Enter this in the OTP input)`, 'success');
          } else {
            showAlert('OTP sent successfully. Check your mobile phone.', 'success');
          }
          
          let counter = 15;
          const interval = setInterval(() => {
            counter--;
            if (counter > 0) {
              btnForgotOTP.innerText = `Resend OTP (${counter}s)`;
            } else {
              clearInterval(interval);
              btnForgotOTP.innerText = 'Forgot OTP? Send Code via SMS';
              btnForgotOTP.disabled = false;
            }
          }, 1000);
        } else {
          btnForgotOTP.disabled = false;
          btnForgotOTP.innerText = 'Forgot OTP? Send Code via SMS';
          showAlert(data.detail || 'Failed to request verification code.');
        }
      } catch (err) {
        btnForgotOTP.disabled = false;
        btnForgotOTP.innerText = 'Forgot OTP? Send Code via SMS';
        showAlert('Failed to connect to verification server.');
      }
    });
  }

  // Handle Form Submission: LOGIN
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();

    const username = document.getElementById('loginUser').value.trim();
    const password = document.getElementById('loginPass').value; // OTP is passed as password to API

    if (!username || !password) {
      showAlert('Mobile Number and OTP Code are required.');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();

      if (response.ok && data.access) {
        localStorage.setItem('e_dairy_token', data.access);
        
        // Fetch user profile info to verify login role match
        const profileResponse = await fetch(`${API_BASE_URL}/profile/`, {
          headers: { 'Authorization': `Bearer ${data.access}` }
        });
        const profile = await profileResponse.json();

        if (profileResponse.ok) {
          const actualRole = profile.profile?.role || 'farmer';
          
          // Verify role matches selected role
          if (actualRole !== currentRole) {
            // Clear token since authorization failed
            localStorage.clear();
            const selectedLabel = currentRole === 'farmer' ? 'Farmer' : 'Collection Centre';
            const actualLabel = actualRole === 'farmer' ? 'Farmer' : 'Collection Centre';
            showAlert(`Unauthorized access. This account is registered as a ${actualLabel}, but you selected ${selectedLabel}.`);
            return;
          }

          localStorage.setItem('e_dairy_user', profile.username);
          localStorage.setItem('e_dairy_role', actualRole);
          
          showAlert('Sign In successful! Redirecting...', 'success');
          
          setTimeout(() => {
            if (actualRole === 'farmer') {
              window.location.href = 'farmer-dashboard.html';
            } else {
              window.location.href = 'agent-dashboard.html';
            }
          }, 1000);
        } else {
          localStorage.clear();
          showAlert('Failed to fetch user profile details.');
        }
      } else {
        showAlert(data.detail || 'Invalid mobile number or verification code.');
      }
    } catch (err) {
      console.error(err);
      showAlert('Failed to connect to authentication server.');
    }
  });

  // Handle Form Submission: REGISTRATION
  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();

    const address = document.getElementById('regAddr').value.trim();
    const phone = regPhoneInput.value.trim();
    const enteredOTP = regPassInput.value.trim();

    // Role-specific name fields
    let first_name = '';
    let last_name = '';
    let farm_name = '';
    if (currentRole === 'farmer') {
      first_name = document.getElementById('regFirst').value.trim();
      last_name = document.getElementById('regLast').value.trim();
      farm_name = document.getElementById('regFarmName').value.trim();
    } else {
      // For collection centre, use centre name as first_name
      first_name = document.getElementById('regCentreName').value.trim();
    }

    if (!phone) {
      showAlert('Phone number is required.');
      return;
    }

    // Verify OTP requested
    if (!lastGeneratedOTP || phone !== targetOTPPhone) {
      showAlert('Please request a verification code first.');
      return;
    }

    // Username is stored as phone number, and password is the OTP
    const payload = {
      username: phone,
      password: enteredOTP,
      email: `${phone}@edairy.com`,
      first_name,
      role: currentRole,
      farmer_code: null,
      phone,
      address
    };
    if (currentRole === 'farmer') {
      payload.last_name = last_name;
      payload.farm_name = farm_name;
    } else {
      // For collection centre, we only need first_name (centre name)
    }

    try {
      const response = await fetch(`${API_BASE_URL}/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();

      if (response.ok) {
        switchTab('login');
        let successMsg = 'Registration successful! You can now sign in using your OTP.';
        if (data.profile && data.profile.role === 'farmer' && data.profile.farmer_code) {
          successMsg = `Registration successful! Your Farmer Code is <strong>${data.profile.farmer_code}</strong>. Please save this code and sign in using your OTP.`;
        }
        showAlert(successMsg, 'success');
        document.getElementById('loginUser').value = phone;
        document.getElementById('loginPass').value = enteredOTP;
      } else {
        let errorMsg = 'Registration failed. Please check your details.';
        if (data.username) {
          errorMsg = `Mobile Number: ${data.username[0]}`;
        } else if (data.password) {
          errorMsg = `Verification Code: ${data.password[0]}`;
        } else if (data.detail) {
          errorMsg = data.detail;
        } else if (typeof data === 'object') {
          const keys = Object.keys(data);
          if (keys.length > 0) {
            errorMsg = `${keys[0]}: ${data[keys[0]][0]}`;
          }
        }
        showAlert(errorMsg);
      }
    } catch (err) {
      console.error(err);
      showAlert('Failed to connect to authentication server.');
    }
  });

  // Check if registration tab was requested via URL search param
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('tab') === 'signup') {
    switchTab('register');
  }

  // Check if user is already logged in
  const existingToken = localStorage.getItem('e_dairy_token');
  const existingRole = localStorage.getItem('e_dairy_role');
  if (existingToken && existingRole) {
    switchRole(existingRole);
    showAlert('You are already signed in. Redirecting...', 'success');
    setTimeout(() => {
      if (existingRole === 'farmer') {
        window.location.href = 'farmer-dashboard.html';
      } else {
        window.location.href = 'agent-dashboard.html';
      }
    }, 1500);
  }

  // Password Visibility Toggle Utility
  function setupPasswordToggle(inputId, toggleId) {
    const input = document.getElementById(inputId);
    const toggleBtn = document.getElementById(toggleId);
    
    if (input && toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';
        
        // Update eye icon SVG dynamically (visible/hidden eye state)
        if (isPassword) {
          toggleBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="20" height="20">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.542-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
            </svg>
          `;
        } else {
          toggleBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" width="20" height="20">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
          `;
        }
      });
    }
  }

  // Setup password triggers
  setupPasswordToggle('loginPass', 'toggleLoginPass');
  setupPasswordToggle('regPass', 'toggleRegPass');
});
