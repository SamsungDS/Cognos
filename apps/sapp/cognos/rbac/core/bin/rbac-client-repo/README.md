# Getting Started with RBAC Client Example

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.


### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

## RBAC Frontend Integration

### Basic Usage (Total ≈ 25 lines)

#### Calling the API

To load a component for easy use using the RBAC Module, we suggest creating a `useEffect` in the desired component in the following fashion:

```javascript
useEffect(() => {
  // STEP 1: Function to load the HTML content from the backend and insert it into the specified element
  const loadComponent = async (path, elementId) => {
    try {
      const response = await axios.get(`${YOUR_MODULE_BACKEND_URL}/api${path}`);
      const contentElement = document.getElementById(elementId);
      contentElement.innerHTML = response.data;
      // Find and run the scripts in the loaded HTML
      const scripts = contentElement.getElementsByTagName('script');
      for (let script of scripts) {
        const newScript = document.createElement('script');
        newScript.textContent = script.textContent;
        document.body.appendChild(newScript);
      }
    } catch (error) {
      console.error('Error loading page:', error);
    }
  };
  // STEP 2: Load login and signup components
  loadComponent('/login', 'loginContent');
  loadComponent('/signup', 'signupContent');
}, []);
```

Using the loadComponent function, for any component you want to get from the RBAC Module, just provide the path and a unique elementId that you can create to reference the component. You can do this for however many components you wish to use from the RBAC Module. Above is an example of how the loadComponent is used to get the login and signup pages from RBAC.

#### Using Component in the Frontend

Insert the component you want to render in a div or section tag with the elementId specified from the loadComponent functions.

```javascript
return (
  <div>
    <div id="loginContent"></div>
    <div id="signupContent"></div>
  </div>
);
```

### Advanced Usage (Total ≈ 32 lines)

#### Navigating to Other Routes on RBAC Success Action:

Ensure the correct navigation route setup has been done in your App.js or any relevant project files. Then add a navigation object in your desired component.

```javascript
const navigate = useNavigate();
```

In the useEffect created in the first step, you can add an event listener to listen for a success event when using RBAC Module Actions.

The event to listen will be 'rbacLogin'.

```javascript
// Event handler for successful login
const handleLoginSuccess = (event) => {
  console.log('Login successful, navigating to profile', event.detail);
  navigate('/profile');
};
// Add event listener for login success
window.addEventListener('rbacLogin', handleLoginSuccess);
// Clean up event listener on component unmount
return () => {
  window.removeEventListener('rbacLogin', handleLoginSuccess);
};
```

Add the navigate object you created to the dependency array of the useEffect.

```javascript
useEffect(() => {
  // ...existing loadComponent logic...

  // Event handler for successful login
  const handleLoginSuccess = (event) => {
    console.log('Login successful, navigating to profile', event.detail);
    navigate('/profile');
  };

  // Add event listener for login success
  window.addEventListener('rbacLogin', handleLoginSuccess);

  // Clean up event listener on component unmount
  return () => {
    window.removeEventListener('rbacLogin', handleLoginSuccess);
  };
}, [navigate]);
```
By following the instructions in this README, you should be able to integrate the RBAC frontend easily and efficiently into your project. If you have any questions or run into issues, please contact repo owner.
