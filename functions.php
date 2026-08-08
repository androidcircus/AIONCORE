// Register Clone Custom Post Type
function register_clone_post_type() {
    $args = array(
        'public' => true,
        'label'  => 'Clones',
        'supports' => array( 'title', 'editor', 'custom-fields' ),
        'show_in_rest' => true,
        'rest_base' => 'clones',
        'menu_icon' => 'dashicons-admin-site',
    );
    register_post_type( 'clone', $args );
}
add_action( 'init', 'register_clone_post_type' );

// Add custom meta fields
function add_clone_meta_boxes() {
    add_meta_box( 'clone_details', 'Clone Details', 'render_clone_meta_box', 'clone', 'normal', 'default' );
}
add_action( 'add_meta_boxes', 'add_clone_meta_boxes' );

function render_clone_meta_box( $post ) {
    $description = get_post_meta( $post->ID, '_clone_description', true );
    $thumb = get_post_meta( $post->ID, '_clone_thumb', true );
    $link = get_post_meta( $post->ID, '_clone_link', true );
    $code = get_post_meta( $post->ID, '_clone_code', true );
    ?>
    <p><label>Description:</label><input type="text" name="clone_description" value="<?php echo esc_attr( $description ); ?>" style="width:100%;" /></p>
    <p><label>Thumbnail URL (or emoji):</label><input type="text" name="clone_thumb" value="<?php echo esc_attr( $thumb ); ?>" style="width:100%;" /></p>
    <p><label>Live Link:</label><input type="url" name="clone_link" value="<?php echo esc_attr( $link ); ?>" style="width:100%;" /></p>
    <p><label>Source Code:</label><textarea name="clone_code" rows="10" style="width:100%; font-family:monospace;"><?php echo esc_textarea( $code ); ?></textarea></p>
    <?php
}

function save_clone_meta( $post_id ) {
    if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) return;
    if ( isset( $_POST['clone_description'] ) ) {
        update_post_meta( $post_id, '_clone_description', sanitize_text_field( $_POST['clone_description'] ) );
    }
    if ( isset( $_POST['clone_thumb'] ) ) {
        update_post_meta( $post_id, '_clone_thumb', sanitize_text_field( $_POST['clone_thumb'] ) );
    }
    if ( isset( $_POST['clone_link'] ) ) {
        update_post_meta( $post_id, '_clone_link', esc_url_raw( $_POST['clone_link'] ) );
    }
    if ( isset( $_POST['clone_code'] ) ) {
        update_post_meta( $post_id, '_clone_code', wp_kses_post( $_POST['clone_code'] ) );
    }
}
add_action( 'save_post', 'save_clone_meta' );

// Expose meta fields to REST API
function register_clone_rest_fields() {
    register_rest_field( 'clone', 'clone_meta', array(
        'get_callback' => function( $post ) {
            return array(
                'description' => get_post_meta( $post['id'], '_clone_description', true ),
                'thumb'       => get_post_meta( $post['id'], '_clone_thumb', true ),
                'link'        => get_post_meta( $post['id'], '_clone_link', true ),
                'code'        => get_post_meta( $post['id'], '_clone_code', true ),
            );
        },
    ) );
}
add_action( 'rest_api_init', 'register_clone_rest_fields' );