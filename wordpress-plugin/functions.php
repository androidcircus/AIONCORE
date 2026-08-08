<?php
/**
 * AION Core - WordPress Plugin
 * Registers a custom "clones" post type and REST endpoint for clone management.
 */

if (!defined('ABSPATH')) exit;

// ---------------------------------------------------------------------------
// Register custom post type
// ---------------------------------------------------------------------------
add_action('init', 'aion_register_clones_post_type');

function aion_register_clones_post_type() {
    register_post_type('clones', array(
        'labels' => array(
            'name'          => 'Clones',
            'singular_name' => 'Clone',
            'add_new_item'  => 'Add New Clone',
            'edit_item'     => 'Edit Clone',
        ),
        'public'       => true,
        'has_archive'  => true,
        'show_in_rest' => true,
        'menu_icon'    => 'dashicons-screenoptions',
        'supports'     => array('title', 'editor', 'thumbnail', 'custom-fields'),
        'rewrite'       => array('slug' => 'clones'),
    ));

    register_meta('clones', 'clone_id', array(
        'type'         => 'string',
        'single'       => true,
        'show_in_rest' => true,
    ));
    register_meta('clones', 'clone_ip', array(
        'type'         => 'string',
        'single'       => true,
        'show_in_rest' => true,
    ));
    register_meta('clones', 'clone_link', array(
        'type'         => 'string',
        'single'       => true,
        'show_in_rest' => true,
    ));
    register_meta('clones', 'clone_thumbnail_id', array(
        'type'         => 'integer',
        'single'       => true,
        'show_in_rest' => true,
    ));
}

// ---------------------------------------------------------------------------
// Display clone card on frontend
// ---------------------------------------------------------------------------
add_filter('the_content', 'aion_clone_card_display', 20);

function aion_clone_card_display($content) {
    if (!is_singular('clones') || !is_main_query()) {
        return $content;
    }

    $clone_id  = get_post_meta(get_the_ID(), 'clone_id', true);
    $clone_ip  = get_post_meta(get_the_ID(), 'clone_ip', true);
    $clone_link = get_post_meta(get_the_ID(), 'clone_link', true);
    $thumb_id  = get_post_meta(get_the_ID(), 'clone_thumbnail_id', true);

    $card = '<div class="aion-clone-card" style="';
    $card .= 'border:1px solid #e0e0e0;border-radius:12px;padding:24px;margin:20px 0;';
    $card .= 'max-width:600px;background:#fafafa;">';

    if ($thumb_id) {
        $card .= wp_get_attachment_image($thumb_id, 'medium', false, array(
            'style' => 'border-radius:8px;width:100%;height:auto;margin-bottom:16px;'
        ));
    }

    $card .= '<h2 style="margin:0 0 8px 0;">' . esc_html(get_the_title()) . '</h2>';
    $card .= '<p style="color:#666;margin:0 0 12px 0;">' . esc_html(get_the_content()) . '</p>';

    if ($clone_ip) {
        $card .= '<p style="font-size:13px;color:#999;margin:4px 0;">VM IP: '
               . esc_html($clone_ip) . '</p>';
    }

    if ($clone_link && $clone_link !== '#') {
        $card .= '<a href="' . esc_url($clone_link) . '" target="_blank" ';
        $card .= 'style="display:inline-block;margin-top:12px;padding:10px 20px;';
        $card .= 'background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;">';
        $card .= 'Launch Clone</a>';
    }

    $card .= '</div>';

    return $card . $content;
}

// ---------------------------------------------------------------------------
// Enqueue styles for archive page
// ---------------------------------------------------------------------------
add_action('wp_enqueue_scripts', 'aion_clone_styles');

function aion_clone_styles() {
    if (is_post_type_archive('clones')) {
        wp_add_inline_style('wp-head', '
            .aion-clone-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:20px; }
            .aion-clone-card { transition: transform 0.2s; }
            .aion-clone-card:hover { transform: translateY(-2px); }
            @media (max-width: 768px) { .aion-clone-grid { grid-template-columns: 1fr; } }
        ');
    }
}

// ---------------------------------------------------------------------------
// REST: list clones as cards
// ---------------------------------------------------------------------------
add_action('rest_api_init', 'aion_register_rest_fields');

function aion_register_rest_fields() {
    register_rest_field('clones', 'featured_image_url', array(
        'get_callback' => function($post) {
            $thumb_id = get_post_thumbnail_id($post['id']);
            if ($thumb_id) {
                return wp_get_attachment_url($thumb_id);
            }
            $meta_thumb = get_post_meta($post['id'], 'clone_thumbnail_id', true);
            if ($meta_thumb) {
                return wp_get_attachment_url($meta_thumb);
            }
            return '';
        },
        'schema' => array('type' => 'string'),
    ));

    register_rest_field('clones', 'clone_meta', array(
        'get_callback' => function($post) {
            return array(
                'clone_id'  => get_post_meta($post['id'], 'clone_id', true),
                'clone_ip'  => get_post_meta($post['id'], 'clone_ip', true),
                'clone_link' => get_post_meta($post['id'], 'clone_link', true),
            );
        },
        'schema' => array('type' => 'object'),
    ));
}
