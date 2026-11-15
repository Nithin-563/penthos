"""Compact reference shapes for the domains a 4B model fumbles most.

Few-shot exemplars work on small models for a specific reason: they transfer
*structure*. A 4B model can describe a fixed-timestep loop but will happily
write `velocity * delta` into a physics step; showing the shape once anchors it.
These are deliberately minimal — a skeleton, not an app — so the model borrows
the architecture without copying the content.

No exemplar is longer than about 30 lines, because prompt tokens are the
scarcest resource on a laptop-sized context.
"""

EXEMPLARS: dict[str, str] = {
    "web": """```html
<header class="site-header">
  <a class="brand" href="/">Project</a>
  <nav aria-label="Primary">
    <a href="#features">Features</a>
    <a href="#pricing">Pricing</a>
  </nav>
</header>

<main id="main">
  <section class="hero" aria-labelledby="hero-title">
    <h1 id="hero-title">One clear promise, stated in one line.</h1>
    <p class="lede">One sentence that explains who this is for and why it helps.</p>
    <a class="button button--primary" href="#start">Start free</a>
  </section>
</main>
```

```css
:root {
  --space-1: 4px; --space-2: 8px; --space-3: 16px; --space-4: 24px;
  --space-5: 32px; --space-6: 48px; --space-7: 64px;
  --text: #16181d; --text-muted: #555b66; --surface: #ffffff;
  --surface-raised: #f5f6f8; --accent: #1f5eff; --radius: 12px;
}
* { box-sizing: border-box; }
body { margin: 0; color: var(--text); background: var(--surface);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif; }
.site-header { display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-3); padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--surface-raised); }
.hero { max-width: 1100px; margin: 0 auto;
  padding: var(--space-7) var(--space-4) var(--space-6); }
h1 { font-size: clamp(2rem, 6vw, 3.25rem); line-height: 1.1; margin: 0 0 var(--space-3); }
.button--primary { display: inline-block; padding: var(--space-2) var(--space-4);
  border-radius: 999px; background: var(--accent); color: #fff;
  text-decoration: none; font-weight: 600; }
.button--primary:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
```""",
    "game": """```text
STEP = 1/60
accumulator = 0
entities = [player, enemies..., tiles]

on_frame(frame_delta):
    accumulator += min(frame_delta, 0.25)        # cap a long stall
    while accumulator >= STEP:                   # fixed updates
        for entity in entities: entity.update(STEP)
        resolve_collisions(entities)             # axis-separated, layers
        accumulator -= STEP
    alpha = accumulator / STEP                   # interpolate rendering
    render(entities, alpha)

player.update(dt):
    axis = input_axis()                          # -1..1, polled
    velocity.x = approach(velocity.x, axis * MAX_SPEED, ACCEL * dt)
    velocity.y += GRAVITY * dt
    if jump_buffered(0.12) and (on_ground or coyote(0.10)):
        velocity.y = JUMP_SPEED; consume_jump()
    move_and_collide(dt)                         # x first, then y

on_hit(entity):
    entity.health -= damage
    freeze_frames(3)                             # ~50ms hit-stop
    shake_camera(2px, 0.1s)
    spawn_particles(entity.position)
    queue_sound("hit", pitch=random(-2, 2))
```""",
    "graphics3d": """```text
# Spaces: model -> world -> view -> clip -> ndc -> screen
model = translate(position) * rotate_y(angle) * scale(size)
view  = inverse(camera_transform)                  # camera at origin, -z forward
proj  = perspective(fov_y, aspect, near, far)      # projection matrix, near > 0

mvp = proj * view * model                          # row-major, one convention
clip = mvp * vec4(local_position, 1.0)
ndc  = clip.xyz / clip.w                           # perspective divide
screen.x = (ndc.x * 0.5 + 0.5) * width
screen.y = (1.0 - (ndc.y * 0.5 + 0.5)) * height

# Normals: inverse-transpose of the model matrix, then normalize.
# Pipeline: vertex -> clip -> rasterize -> depth test -> fragment -> blend
# Opaque front-to-back; transparent back-to-front; depth test always on.
```""",
}


def exemplar_for(domain: str | None) -> str:
    """Return the reference shape for a domain, or an empty string."""
    return EXEMPLARS.get(domain or "", "")
