document.addEventListener('DOMContentLoaded', () => {
  const header = document.querySelector('header');
  const menuToggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('nav');
  const navLinks = document.querySelectorAll('nav a');

  // API Configuration
  const API_BASE_URL = window.location.origin + '/api';

  // Modal DOM Elements
  const authModal = document.getElementById('authModal');
  const modalCloseBtn = document.getElementById('modalCloseBtn');
  const tabLoginBtn = document.getElementById('tabLoginBtn');
  const tabRegisterBtn = document.getElementById('tabRegisterBtn');
  const homeLoginForm = document.getElementById('homeLoginForm');
  const homeRegisterForm = document.getElementById('homeRegisterForm');
  const modalAlert = document.getElementById('modalAlert');
  
  const regRole = document.getElementById('regRole');
  const regCodeGroup = document.getElementById('regCodeGroup');

  // Handle header background change on scroll
  window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
      header.classList.add('scrolled');
    } else {
      header.classList.remove('scrolled');
    }
    updateActiveNav();
  });

  // Mobile navigation menu toggle
  if (menuToggle && nav) {
    menuToggle.addEventListener('click', () => {
      nav.classList.toggle('active');
      
      const spans = menuToggle.querySelectorAll('span');
      if (nav.classList.contains('active')) {
        spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
        spans[1].style.opacity = '0';
        spans[2].style.transform = 'rotate(-45deg) translate(6px, -6px)';
      } else {
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }
    });
  }

  // Close mobile nav when clicking a link
  navLinks.forEach(link => {
    link.addEventListener('click', () => {
      if (nav.classList.contains('active')) {
        nav.classList.remove('active');
        const spans = menuToggle.querySelectorAll('span');
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }
    });
  });

  // Highlight active section based on scroll offset
  function updateActiveNav() {
    if (window.scrollY < 200) {
      navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === '#home') {
          link.classList.add('active');
        }
      });
    }
  }
  
  // Set active link on click
  navLinks.forEach(link => {
    link.addEventListener('click', () => {
      navLinks.forEach(l => l.classList.remove('active'));
      link.classList.add('active');
    });
  });

  /* ==========================================================================
     AUTHENTICATION MODAL FLOW & API INTEGRATION
     ========================================================================== */

  // Helper: Show alert in modal
  function showAlert(message, type = 'danger') {
    modalAlert.innerText = message;
    modalAlert.className = `modal-alert ${type}`;
    modalAlert.style.display = 'block';
  }

  // Helper: Clear alert
  function clearAlert() {
    modalAlert.innerText = '';
    modalAlert.style.display = 'none';
  }

  // Helper: Open Modal
  function openAuthModal() {
    clearAlert();
    authModal.classList.add('active');
  }

  // Helper: Close Modal
  function closeAuthModal() {
    authModal.classList.remove('active');
    homeLoginForm.reset();
    homeRegisterForm.reset();
  }

  // Toggle Farmer Code field based on selected role
  if (regRole && regCodeGroup) {
    regRole.addEventListener('change', () => {
      if (regRole.value === 'farmer') {
        regCodeGroup.style.display = 'block';
        document.getElementById('regCode').setAttribute('required', 'true');
      } else {
        regCodeGroup.style.display = 'none';
        document.getElementById('regCode').removeAttribute('required');
      }
    });
  }

  // Setup click triggers on main pages
  const loginBtnHeader = document.getElementById('btn-header-login');
  const trialBtnHero = document.getElementById('btn-hero-trial');

  if (loginBtnHeader) {
    loginBtnHeader.addEventListener('click', (e) => {
      e.preventDefault();
      openAuthModal();
    });
  }

  if (trialBtnHero) {
    trialBtnHero.addEventListener('click', (e) => {
      e.preventDefault();
      openAuthModal();
    });
  }

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeAuthModal);
  }

  // Close when clicking overlay background
  authModal.addEventListener('click', (e) => {
    if (e.target === authModal) {
      closeAuthModal();
    }
  });

  // Tab switching: Login Tab
  function switchToLoginTab() {
    clearAlert();
    tabLoginBtn.classList.add('active');
    tabRegisterBtn.classList.remove('active');
    homeLoginForm.classList.add('active');
    homeRegisterForm.classList.remove('active');
  }

  // Tab switching: Register Tab
  function switchToRegisterTab() {
    clearAlert();
    tabRegisterBtn.classList.add('active');
    tabLoginBtn.classList.remove('active');
    homeRegisterForm.classList.add('active');
    homeLoginForm.classList.remove('active');
  }

  if (tabLoginBtn) tabLoginBtn.addEventListener('click', switchToLoginTab);
  if (tabRegisterBtn) tabRegisterBtn.addEventListener('click', switchToRegisterTab);

  const switchToRegLink = document.getElementById('switchToRegister');
  const switchToLoginLink = document.getElementById('switchToLogin');

  if (switchToRegLink) switchToRegLink.addEventListener('click', switchToRegisterTab);
  if (switchToLoginLink) switchToLoginLink.addEventListener('click', switchToLoginTab);

  // Form submission: REGISTRATION
  homeRegisterForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();

    const username = document.getElementById('regUser').value;
    const password = document.getElementById('regPass').value;
    const first_name = document.getElementById('regFirst').value;
    const last_name = document.getElementById('regLast').value;
    const role = regRole.value;
    const farmer_code = document.getElementById('regCode').value;
    const phone = document.getElementById('regPhone').value;
    const address = document.getElementById('regAddr').value;

    if (role === 'farmer' && !farmer_code) {
      showAlert('Farmer code is required for farmers.');
      return;
    }

    const payload = {
      username,
      password,
      email: `${username}@edairy.com`,
      first_name,
      last_name,
      role,
      farmer_code,
      phone,
      address
    };

    try {
      const response = await fetch(`${API_BASE_URL}/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();

      if (response.ok) {
        switchToLoginTab();
        showAlert('Registration successful! You can now log in.', 'success');
        document.getElementById('loginUser').value = username;
        document.getElementById('loginPass').value = password;
      } else {
        const errorMsg = data.username ? `Username: ${data.username[0]}` : 
                         data.farmer_code ? `Farmer Code: ${data.farmer_code[0]}` : 
                         'Registration failed. Please check details.';
        showAlert(errorMsg);
      }
    } catch (err) {
      showAlert('Failed to connect to authentication server.');
    }
  });

  // Form submission: LOGIN
  homeLoginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();

    const username = document.getElementById('loginUser').value;
    const password = document.getElementById('loginPass').value;

    try {
      const response = await fetch(`${API_BASE_URL}/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await response.json();

      if (response.ok && data.access) {
        localStorage.setItem('e_dairy_token', data.access);
        
        // Fetch user info profile
        const profileResponse = await fetch(`${API_BASE_URL}/profile/`, {
          headers: { 'Authorization': `Bearer ${data.access}` }
        });
        const profile = await profileResponse.json();

        if (profileResponse.ok) {
          localStorage.setItem('e_dairy_user', profile.username);
          localStorage.setItem('e_dairy_role', profile.profile?.role || 'farmer');
          
          closeAuthModal();
          updateNavbarAuth();
        }
      } else {
        showAlert(data.detail || 'Invalid username or password.');
      }
    } catch (err) {
      showAlert('Failed to connect to authentication server.');
    }
  });

  // Navbar authentication status check
  function updateNavbarAuth() {
    const token = localStorage.getItem('e_dairy_token');
    const userNavCta = document.querySelector('.nav-cta');
    if (!userNavCta) return;

    if (token) {
      userNavCta.innerHTML = `
        <a href="api-test.html" class="btn btn-login" style="background:var(--accent); color:var(--white);" id="btn-header-dash">Open Panel</a>
        <button class="btn btn-outline-secondary" id="btn-header-logout" style="border-radius:30px; margin-left: 12px; padding: 8px 18px; font-size:14px; font-weight:600; cursor:pointer; background:none; border:1px solid rgba(82,59,139,0.15); transition:var(--transition);">Logout</button>
      `;
      
      // Hook logout listener
      document.getElementById('btn-header-logout').addEventListener('click', () => {
        localStorage.removeItem('e_dairy_token');
        localStorage.removeItem('e_dairy_user');
        localStorage.removeItem('e_dairy_role');
        
        // Restore standard Login link
        userNavCta.innerHTML = `
          <a href="#login" class="btn btn-login" id="btn-header-login">Login</a>
        `;
        
        // Rehook click event
        document.getElementById('btn-header-login').addEventListener('click', (e) => {
          e.preventDefault();
          openAuthModal();
        });
      });
    }
  }

  // Run navbar check on load
  updateNavbarAuth();
});
