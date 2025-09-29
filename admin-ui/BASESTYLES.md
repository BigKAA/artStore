# @artstore-admin-ui Base Styles

This document outlines the base styles, component styles, and utility classes used in the `@artstore-admin-ui` project.


## Global Styles

The global styles are defined in `src/styles.scss` and apply to the entire application.

| Selector | Property | Value | Description |
| :--- | :--- | :--- | :--- |
| `body` | `font-family` | `'Segoe UI', Tahoma, Geneva, Verdana, sans-serif` | Sets the default font for the application. |
| `body` | `background-color` | `#f8f9fa` | Sets the default background color. |

## Base Components

### Card

Custom styles for `.card` elements to provide a consistent look and feel.

| Selector | Property | Value | Description |
| :--- | :--- | :--- | :--- |
| `.card` | `border-radius` | `12px` | Applies rounded corners to the cards. |
| `.card` | `box-shadow` | `0 0 15px rgba(0, 0, 0, 0.1)` | Adds a subtle shadow effect. |
| `.card` | `border` | `none` | Removes the default border. |
| `.card` | `transition` | `all 0.2s ease-in-out` | Smooth transition for hover effects. |
| `.card:hover` | `box-shadow` | `0 5px 20px rgba(0, 0, 0, 0.15)` | Enhances the shadow on hover for a "lifting" effect. |


### Notification

Styles for the notification component, which is used to display alerts and messages to the user.

| Class | Description |
| :--- | :--- |
| `.notification-container` | A fixed container at the top-right of the screen to hold notification items. |
| `.notification-item` | Individual notification element with custom shadow, padding, and animations. |
| `.notification-title` | Styles for the title of the notification. |
| `.notification-message` | Styles for the main message content. |
| `.alert-success` | Styles for success notifications, typically with a green color scheme. |
| `.alert-danger` | Styles for error notifications, typically with a red color scheme. |
| `.alert-warning` | Styles for warning notifications, typically with a yellow color scheme. |
| `.alert-info` | Styles for informational notifications, typically with a blue color scheme. |

**Animations:**

| Animation | Description |
| :--- | :--- |
| `slideInRight` | Slides the notification in from the right. |
| `slideOutRight`| Slides the notification out to the right. |


## Page: Storage Elements

Styles for the Storage Elements page, located in `src/app/pages/storage-elements/storage-elements.scss`.

### Layout and Sections

| Class | Description |
| :--- | :--- |
| `.storage-elements-page` | Main container for the page. |
| `.stats-grid` | Grid for displaying statistics cards. |
| `.filters-section` | A dedicated section for filtering and search controls. |
| `.elements-table` | Container for the main data table. |
| `.loading-state` | Styles for the loading indicator. |
| `.empty-state` | Styles for when there is no data to display. |

### Components

| Class | Description |
| :--- | :--- |
| `.stat-card` | Cards for displaying key statistics. Includes a hover effect. |
| `.stat-card-compact` | A more compact version of the statistics card. |
| `.modal` | Custom styles for modal dialogs, including headers, body, and footers. |

### Table Styles

| Selector | Description |
| :--- | :--- |
| `table` | General table styling within `.elements-table`. |
| `tbody tr:hover` | Highlight effect for table rows on hover. |
| `td code` | Styling for `<code>` elements within table cells. |
| `.badge` | Custom styles for badges, with color variations. |

### Utility and Status Classes

| Class | Description |
| :--- | :--- |
| `.text-truncate` | Truncates text with an ellipsis. |
| `.cursor-pointer` | Changes the cursor to a pointer. |
| `.status-online` | Green text for "online" status. |
| `.status-offline` | Gray text for "offline" status. |
| `.status-error` | Red text for "error" status. |
| `.mode-rw` | Green text for "Read/Write" mode. |
| `.mode-ro` | Yellow text for "Read-Only" mode. |
| `.mode-cold` | Blue text for "Cold Storage" mode. |

### Animations

| Animation | Description |
| :--- | :--- |
| `fadeIn` | A fade-in effect applied to stat cards and table rows. |


## Page: Users

This page has a rich set of styles defined in `src/app/pages/users/users.scss`.

### CSS Variables

The component uses local CSS variables (`:host`) for easy customization of common properties.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `--users-table-row-height`| `72px` | Sets the minimum height for table rows. |
| `--users-avatar-size` | `36px` | The size (width and height) of user avatars. |
| `--users-action-btn-size` | `32px` | The size of action buttons in the user table. |
| `--users-modal-width` | `600px` | The default max-width for user-related modals. |
| `--users-transition` | `0.2s ease` | The default transition for animations. |

### Components and Sections

| Class | Description |
| :--- | :--- |
| `.users-stats` | Container for statistics cards with gradient backgrounds. |
| `.search-filters-card` | A card containing search and filter controls. |
| `.users-table` | The main container for the users data table. |
| `.pagination-controls` | Styling for pagination elements. |
| `.empty-state` | A well-defined state for when no users are found. |

### User Table Details

| Class | Description |
| :--- | :--- |
| `.user-avatar` | Circular user avatars with gradient backgrounds based on user status (`.user-active`, `.user-admin`, `.user-inactive`). |
| `.user-info` | Styles for user name, username, and description. |
| `.user-status-badge`| Gradient badges for user status (`.status-active`, `.status-admin`, `.status-inactive`). |
| `.group-tag` | Small tags to indicate user groups. |
| `.provider-tag`| Small tags to indicate auth providers. |
| `.user-actions` | Styles for the dropdown menu with user-specific actions. |

### Animations

| Animation | Description |
| :--- | :--- |
| `slideDown` | A slide-down effect used for revealing the filters section. |
