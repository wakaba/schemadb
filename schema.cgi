#!/usr/bin/perl
use strict;
#use warnings;
use Path::Class;
use lib glob file (__FILE__)->dir->subdir ('modules/*/lib');
use Encode;
use Wanage::URL;
use Wanage::HTTP;
use Warabe::App;
use Web::URL::Canonicalize qw(url_to_canon_url);

my $data_directory = './data/';
my $data_directory_back = '../';
my $map_directory = $data_directory;
my $lock_file_name = $data_directory . '.lock';

sub resolve_url ($$) {
  my $base = defined $_[1] ? url_to_canon_url $_[1], 'about:blank' : 'about:blank';
  return url_to_canon_url $_[0], $base;
} # resolve_url

sub psgi_app () {
  return sub {
    my $http = Wanage::HTTP->new_from_psgi_env ($_[0]);
    my $app = Warabe::App->new_from_http ($http);

    # XXX accesslog
    warn sprintf "ACCESS: [%s] %s %s FROM %s %s\n",
        scalar gmtime,
        $app->http->request_method, $app->http->url->stringify,
        $app->http->client_ip_addr->as_text,
        $app->http->get_request_header ('User-Agent') // '';

    $app->http->set_response_header
        ('Strict-Transport-Security' => 'max-age=10886400; includeSubDomains; preload');

    return $http->send_response (onready => sub {
      $app->execute (sub {
        return $app->throw_error (405, reason_phrase => 'Read-only mode')
            if $ENV{SCHEMADB_READ_ONLY} and
               not $app->http->request_method eq 'GET';
        return __PACKAGE__->main ($app);
      });
    });
  };
} # psgi_app

sub main ($$) {
  my ($class, $app) = @_;
  my $path = $app->path_segments;

  if (@$path == 2 and $path->[0] =~ /\A[0-9a-f]+\z/) {
    if ($path->[1] eq 'cache.dat') {
      # /{key}/cache.dat
      my $file_text = get_file_text ($path->[0]);
      if (defined $file_text) {
        my $prop = get_prop_hash ($path->[0]);
        $app->http->set_status (203);
        my $ct = $prop->{content_type}->[0]
            ? $prop->{content_type}->[0]->[0]
            : 'application/octet-stream';
        if ($prop->{charset}->[0]) {
          $ct .= '; charset="' . $prop->{charset}->[0]->[0] . '"';
        }
        $ct =~ s/[\x09\x0A\x0D]+/ /g;
        $ct =~ s/[^\x20-\x7E]+//g;
        $app->http->set_response_header ('Content-Type' => $ct);
        my $file_name = $prop->{file_name}->[0]
            ? $prop->{file_name}->[0]->[0] : '';
        $file_name =~ s/[\x09\x0A\x0D]+/ /g;
        $file_name =~ s/[^\x20-\x7E]+//g;
        if (length $file_name) {
          $file_name =~ s/\\/\\\\/g;
          $file_name =~ s/"/\\"/g;
          $app->http->set_response_header
              (q[Content-Disposition] => qq[inline; filename="$file_name"]);
        }
        my $lm = $prop->{last_modified}->[0]
            ? rfc3339_to_http ($prop->{last_modified}->[0]->[0]) : '';
        if (length $lm) {
          $app->http->set_response_header ('Last-Modified' => $lm);
        }
        $app->http->set_response_header ('Content-Security-Policy' => 'sandbox');
        $app->http->send_response_body_as_ref (\$file_text);
        $app->http->close_response_body;
        return;
      }
    } elsif ($path->[1] eq 'cache.html') {
      # /{key}/cache.html
      my $file_text = get_file_text ($path->[0]);
      if (defined $file_text) {
        my ($title_text, $title_lang) = get_title ($path->[0]);
        $title_text = htescape ($title_text);
        $title_lang = htescape ($title_lang);
        $app->http->set_response_header
            ('Content-Type' => 'text/html; charset=utf-8');
        $app->http->send_response_body_as_text
            (qq[<!DOCTYPE HTML>
<html lang="en">
<head>
<title lang="$title_lang">$title_text</title>
<link rel=stylesheet href="../../schema-style">
<script src="../../schema-annotation"></script>
</head>
<body>
<h1 lang="$title_lang">$title_text</h1>

<div id=status class=error>Scripting is disabled and therefore
annotations cannot be shown.</div>

<pre><code>]);
        my $i = 1;
        for (split /\x0D?\x0A/, $file_text) {
          $app->http->send_response_body_as_text
              (qq[<span class=line id=line-@{[$i++]}>] . htescape ($_) . qq[</span>\n]);
        }
        $app->http->send_response_body_as_text (qq[</code></pre>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', $path->[0]));
        $app->http->close_response_body;
        return;
      }
      
    } elsif ($path->[1] eq 'prop.txt') {
      # /{key}/prop.txt
      if ($app->http->request_method eq 'PUT') {
        lock_start ();
        ## TODO: CONTENT_TYPE check
        my $old_prop = get_prop_hash ($path->[0]);
        my $prop_text = Encode::decode ('utf-8', ${$app->http->request_body_as_ref});
        if (set_prop_text ($path->[0], $prop_text, new_file => 0)) {
          delete_from_maps ($path->[0] => $old_prop);
          my $prop = get_prop_hash ($path->[0]);
          update_maps ($path->[0] => $prop);
          $app->send_error (201);
          commit_changes ();
          return;
        }
      } else {
        my $prop_text = get_prop_text ($path->[0]);
        if (defined $prop_text) {
          $app->send_plain_text ($prop_text);
          return;
        }
      }
    } elsif ($path->[1] eq 'prop.html') {
      # /{key}/prop.html
      my $prop = get_prop_hash ($path->[0]);
      if (keys %$prop) {
        $app->http->set_response_header
            ('Content-Type' => 'text/html; charset=utf-8');

        my ($title_text, $title_lang) = get_title ($path->[0]);
        $title_text = htescape ($title_text);
        $title_lang = htescape ($title_lang);

        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title lang="$title_lang">Information on $title_text</title>
<link rel=stylesheet href="../../schema-style">
</head>
<body>
<h1 lang="$title_lang">Information on $title_text</h1>
]);

        my %keys = map {$_ => 1} keys %$prop;

        $app->http->send_response_body_as_text (qq[<dl>]);

        if ($prop->{uri}->[0]) {
          $app->http->send_response_body_as_text (qq[<dt lang="en">URI</dt>]);
          for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{uri}}) {
            my $uri = $v->[0];
            my $etime = '';
            if ($uri =~ s/<>(.*)$//s) {
              $etime = htescape ($1);
            }
            my $euri = htescape ($uri);
            my $elang = htescape ($v->[1]);
            $app->http->send_response_body_as_text (qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">$euri</a>&gt;</code>]);
            
            my $uri2 = q<../list/uri.html?> . percent_encode_c $uri;
            $app->http->send_response_body_as_text (qq[ [<a href="@{[htescape ($uri2)]}" lang="en">more</a>]]);
            
            if (length $etime) {
              $app->http->send_response_body_as_text (qq[ (<time>$etime</time>)]);
            }
            $app->http->send_response_body_as_text (qq[</dd>]);
          }
          delete $keys{uri};
        }

        if ($prop->{public_id}->[0]) {
          $app->http->send_response_body_as_text (qq[<dt lang="en">Public Identifier</dt>]);
          for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{public_id}}) {
            my $uri = q<../list/pubid.html?> . percent_encode_c $v->[0];
            my $elang = htescape ($v->[1]);
            $app->http->send_response_body_as_text (qq[<dd><a href="@{[htescape ($uri)]}"><code lang="@{[htescape ($v->[1])]}" class=public-id>@{[htescape ($v->[0])]}</code></a></dd>]);
          }
          delete $keys{public_id};
        }

        if ($prop->{system_id}->[0]) {
          $app->http->send_response_body_as_text (qq[<dt lang="en">System Identifier</dt>]);
          for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{system_id}}) {
            my $uri = $v->[0];
            if (defined $prop->{base_uri}->[0]) {
              $uri = resolve_url $uri, $prop->{base_uri}->[0]->[0];
            }
            my $euri = htescape ($uri);
            my $elang = htescape ($v->[1]);
            $app->http->send_response_body_as_text (qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">@{[htescape ($v->[0])]}</a>&gt;</code>]);
            
            my $uri2 = q<../list/uri.html?> . percent_encode_c $uri;
            $app->http->send_response_body_as_text (qq[ [<a href="@{[htescape ($uri2)]}" lang="en">more</a>]]);
          }
          delete $keys{system_id};
        }

        for ([tag => 'Tag']) {
          my $key = $_->[0];
          my $label = $_->[1];
          if ($prop->{$key}) {
            $app->http->send_response_body_as_text
                (qq[<dt lang="en" class="$key">$label</dt>]);
            for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{$key}}) {
              my $uri = q<../list/tag.html?> . percent_encode_c $v->[0];
              my $elang = htescape ($v->[1]);
              $app->http->send_response_body_as_text (qq[<dd class="$key"><a href="@{[htescape ($uri)]}" lang="@{[htescape ($v->[1])]}">@{[htescape ($v->[0])]}</a></dd>]);
            }
            delete $keys{$key};
          }
        }

        for ([editor => 'Editor'], [editor_mail => 'Editor (mail)'],
             [rcs_user => 'Editor (RCS)'],
             [author => 'Author'], [author_mail => 'Author (mail)']) {
          my $key = $_->[0];
          my $label = $_->[1];
          if ($prop->{$key}) {
            $app->http->send_response_body_as_text (qq[<dt lang="en">$label</dt>]);
            for my $v (@{$prop->{$key}}) {
              my $uri = q<../list/editor.html?> . percent_encode_c $v->[0];
              my $elang = htescape ($v->[1]);
              $app->http->send_response_body_as_text (qq[<dd><a href="@{[htescape ($uri)]}" lang="@{[htescape ($v->[1])]}">@{[htescape ($v->[0])]}</a></dd>]);
            }
            delete $keys{$key};
          }
        }

        for ([src => 'Source'],
             [contains => 'Contains'],
             [derived_from => 'Derived from'],
             [ref => 'Reference'],
             [documentation => 'Documentation'],
             [related => 'Related file']) {
          my $key = $_->[0];
          my $label = $_->[1];
          if ($prop->{$key}->[0]) {
            $app->http->send_response_body_as_text (qq[<dt>] . $label . q[</dt>]);
            for (@{$prop->{$key}}) {
              my $v = $_->[0];
              $app->http->send_response_body_as_text (qq[<dd><dl>]);
              for (split /\s*;\s*/, $v) {
                my ($n, $v) = split /\s*:\s*/, $_, 2;
                my $l = '';
                if ($n =~ s/\@([^@]*)$//) {
                  $l = $1;
                }
                if ($n eq 'public_id') {
                  $app->http->send_response_body_as_text (qq[<dt>Public Identifier</dt><dd>]);
                  my $uri = q<../list/pubid.html?> . percent_encode_c $v;
                  $app->http->send_response_body_as_text (qq[<a href="@{[htescape ($uri)]}"><code class=public-id lang="@{[htescape ($l)]}">@{[htescape ($v)]}</code></a></dd>]);
                } elsif ($n eq 'system_id' or $n eq 'uri') {
                  $app->http->send_response_body_as_text (qq[<dt>]);
                  $app->http->send_response_body_as_text
                      ({system_id => 'System Identifier',
                        uri => 'URI'}->{$n});
                  $app->http->send_response_body_as_text (qq[</dt><dd>]);
                  my $v_uri = resolve_url $v, $prop->{base_uri}->[0] ? $prop->{base_uri}->[0]->[0] : undef;
                  my $uri = q<../list/uri.html?> . percent_encode_c $v_uri;
                  $app->http->send_response_body_as_text (qq[<code class=uri lang="@{[htescape ($l)]}">&lt;<a href="@{[htescape ($uri)]}">@{[htescape ($v)]}</a>&gt;</code></dd>]);
                } elsif ($n eq 'digest') {
                  $app->http->send_response_body_as_text (qq[<dt>File</dt><dd>]);
                  my ($title_text, $title_lang) = get_title ($v);
                  my $uri = q<../> . $v . q</prop.html>;
                  $app->http->send_response_body_as_text (qq[<a lang="@{[htescape ($title_lang)]}" href="@{[htescape ($uri)]}">@{[htescape ($title_text)]}</a>]);
                  $app->http->send_response_body_as_text (qq[ [<a href="diff/@{[htescape ($v)]}.html">Diff</a>]]);
                } else {
                  $app->http->send_response_body_as_text (qq[<dt>] . htescape ($n));
                  $app->http->send_response_body_as_text (qq[<dd lang="@{[htescape ($l)]}">] . htescape ($v));
                }
              }
              $app->http->send_response_body_as_text (qq[</dl></dd>]);
            }
            delete $keys{$key};
          }
        }

        for my $key (sort {$a cmp $b} keys %keys) {
          next unless @{$prop->{$key}};
          $app->http->send_response_body_as_text (qq[<dt>] . htescape ($key));
          for (@{$prop->{$key}}) {
            $app->http->send_response_body_as_text (qq[<dd lang="@{[htescape ($_->[1])]}">]);
            $app->http->send_response_body_as_text (htescape ($_->[0]));
          }
        }

        $app->http->send_response_body_as_text (qq[<dt>MD5 Digest</dt><dd><code>$path->[0]</code></dd>\n]);
        $app->http->send_response_body_as_text (qq[</dl>]);

        if (defined $prop->{content_type}->[0] and
            ($prop->{content_type}->[0]->[0] eq 'application/zip' or
             $prop->{content_type}->[0]->[0] =~ /\+zip$/)) {
          $app->http->send_response_body_as_text (q[<form action=expand method=post><p><button type=submit>Expand</button></p></form>]);
        }

        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', $path->[0]));
        $app->http->close_response_body;
        return;
      }
    } elsif ($path->[1] eq 'propedit.html') {
      # /{key}/propedit.html
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      my $f = file (__FILE__)->dir->file ('prop-edit.en.html');
      $app->http->send_response_body_as_ref (\scalar $f->slurp);
      $app->http->close_response_body;
      return;
    } elsif ($path->[1] eq 'expand') {
      # /{key}/expand
      if ($app->http->request_method eq 'POST') {
        lock_start ();
        my $prop = get_prop_hash ($path->[0]);
        if (defined $prop->{content_type}->[0] and
            ($prop->{content_type}->[0]->[0] eq 'application/zip' or
             $prop->{content_type}->[0]->[0] =~ /\+zip$/)) {
          my $prop = get_prop_hash ($path->[0]);
          my $file_name = get_file_name ($path->[0]);
          require Archive::Zip;
          my $zip = Archive::Zip->new;
          my $error_code = $zip->read($file_name);
          if ($error_code == Archive::Zip::AZ_OK ()) {
            $app->http->set_status (201);
            $app->http->set_response_header
                ('Content-Type' => 'text/html; charset=utf-8');
            $app->http->send_response_body_as_text
                (qq[<!DOCTYPE HTML><html lang=""><title>201 Created</title><ul>]);
            for my $member ($zip->members) {
              next if $member->isDirectory;
              my $ent = {};
              $ent->{file_name} = $member->fileName;
              $ent->{last_modified} = time_to_rfc3339 ($member->lastModTime);
              $ent->{digest} = $path->[0];
              $ent->{s} = $member->contents;
              my $digest = add_entity ($ent);
              my $uri = '../'.$digest.q</prop.html>;
              $app->http->send_response_body_as_text (qq[<li><a href="@{[htescape ($uri)]}"><code class=file>@{[htescape ($ent->{file_name})]}</code></a></li>]);
              add_prop ($prop, 'contains', 'digest:'.$digest, '');
            }
            $app->http->send_response_body_as_text (qq[</ul>]);
            set_prop_hash ($path->[0], $prop);
            $app->http->close_response_body;
            commit_changes ();
            return;
          } else {
            return $app->send_error (400, reason_phrase => "Not expandable ($error_code)");
          }
        } else {
          return $app->send_error (400);
        }
      } else {
        return $app->send_error (405);
      }

    } elsif ($path->[1] eq 'annotation.txt') {
      # /{key}/annotation.txt
      if ($app->http->request_method eq 'POST') {
        $app->http->send_plain_text (time . (int (rand (10)), int (rand (10)), int (rand (10))));
        return;
      } else {
        my $prop = get_prop_hash ($path->[0]);
        $app->http->set_response_header
            ('Content-Type' => 'text/plain; charset=utf-8');
        for (@{$prop->{an} or []}) {
          $app->http->send_response_body_as_text ($_->[0] . "\n");
        }
        $app->http->close_response_body;
        return;
      }
    }

  } elsif (@$path == 3 and $path->[0] =~ /\A[0-9a-f]+\z/) {
    if ($path->[1] eq 'annotation' and
        $path->[2] =~ /\A([0-9A-Za-z]+)\.txt\z/) {
      # /{key}/annotation/{id}.txt
      my $id = $1;
      if ($app->http->request_method eq 'PUT') {
        lock_start ();
        my $prop = get_prop_hash ($path->[0]);
        for my $v (@{$prop->{an} or []}) {
          if ($v->[0] =~ /^\Q$id\E(?>$|\t)/) {
            ## TODO: Check CONTENT_TYPE
            $v->[0] = Encode::decode ('utf-8', ${$app->http->request_body_as_ref});
            set_prop_hash ($path->[0], $prop);
            $app->send_error (201);
            commit_changes ();
            return;
          }
        }
        push @{$prop->{an} ||= []},
            [Encode::decode ('utf-8', ${$app->http->request_body_as_ref}), ''];
        set_prop_hash ($path->[0], $prop);
        $app->send_error (201);
        commit_changes ();
        return;
      } else {
        return $app->send_error (405);
      }
    } elsif ($path->[1] eq 'annotation' and $path->[2] =~ /\A[0-9A-Za-z]+\z/) {
      # /{key}/annotation/{id}
      if ($app->http->request_method eq 'DELETE') {
        lock_start ();
        my $prop = get_prop_hash ($path->[0]);
        for my $i (0..$#{$prop->{an} or []}) {
          my $v = $prop->{an}->[$i];
          if ($v->[0] =~ /^\Q$path->[2]\E(?>$|\t)/) {
            splice @{$prop->{an}}, $i, 1, ();
            set_prop_hash ($path->[0], $prop);
            $app->http->set_status (200, reason_phrase => 'Deleted');
            commit_changes ();
            return;
          }
        }
        $app->http->set_status (200, reason_phrase => 'Deleted');
        return
      } else {
        return $app->send_error (405);
      }
    } elsif ($path->[1] eq 'diff' and $path->[2] =~ /\A([0-9a-f]+)\.html\z/) {
      # /{key}/diff/{key}.html
      my $digest = $1;
      ## TODO: charset
      my $from_text = [split /\x0D?\x0A/, get_file_text ($digest)];
      my $to_text = [split /\x0D?\x0A/, get_file_text ($path->[0])];
      my $etitlea = htescape (get_title ($digest));
      my $etitleb = htescape (get_title ($path->[0]));
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Diff between "$etitlea" and "$etitleb"</title>
<link rel=stylesheet href="../../../schema-style">
</head>
<body>
<h1>Diff between 
<a href="../../@{[htescape ($digest)]}/prop.html"><cite>$etitlea</cite></a> and 
<a href="../prop.html"><cite>$etitleb</cite></a></h1>

<pre><code>]);
      require Algorithm::Diff;
      my $diff = Algorithm::Diff->new ($from_text, $to_text);
      while ($diff->Next) {
        if ($diff->Same) {
          $app->http->send_response_body_as_text
              (qq[<span class=line>] . htescape ($_) . qq[</span>\n])
                  for $diff->Items (1);
        } else {
          $app->http->send_response_body_as_text
              (qq[<del><span class=line>] . htescape ($_) . qq[</span></del>\n])
                  for $diff->Items (1);
          $app->http->send_response_body_as_text
              (qq[<ins><span class=line>] . htescape ($_) . qq[</span></ins>\n])
                  for $diff->Items (2);
        }
      }

      my $no_sync_pattern = qr/
        charset|content_type|
        base_uri|uri|
        derived_from|src|
        documentation|documentation_uri|
        last_modified|modified_in_content|
        rcs_date|rcs_revision|rcs_user|
        label
      /x;

      my $edigest_old = htescape ($digest);
      my $edigest_new = htescape ($path->[9]);
      $app->http->send_response_body_as_text (qq[
      </code></pre>
      
      <details id=diff-props>
      <legend>Properties</legend>

      <form action="../diff-sync/$edigest_old" method=post
          accept-charset=utf-8>
      <table class=diff-props>
      <thead>
      <tr><th><a href="../../$edigest_old/prop.html"><cite>$etitlea</cite></a>
      <th><a href="../prop.html"><cite>$etitleb</cite></a>

      <tbody>]);
      
      my $from_prop_text = [grep {length $_}
                            split /\x0D?\x0A/,
                            get_normalized_prop_text ($digest)];
      my $to_prop_text = [grep {length $_}
                          split /\x0D?\x0A/,
                          get_normalized_prop_text ($path->[0])];
      my $diff = Algorithm::Diff->new ($from_prop_text, $to_prop_text);
      while ($diff->Next) {
        if ($diff->Same) {
          $app->http->send_response_body_as_text
              (qq[<tr><td colspan=2><code>] . htescape ($_) . q[</code>])
                  for $diff->Items (1);
        } else {
          for ($diff->Items (1)) {
            my $ev = htescape ($_);
            $app->http->send_response_body_as_text
                (qq[<tr><td><del><code>$ev</code></del>]);
            my $checked = $ev =~ /^(?:$no_sync_pattern)[\@:]/ ? '' : 'checked';
            $app->http->send_response_body_as_text
                (qq[<td><label><input type=checkbox name=prop-new value="$ev"
                   $checked> Add this property</label>]);
          }
          for ($diff->Items (2)) {
            my $ev = htescape ($_);
            my $checked = $ev =~ /^(?:$no_sync_pattern)[\@:]/ ? '' : 'checked';
            $app->http->send_response_body_as_text
                (qq[<tr><td><label><input type=checkbox name=prop-old
                   value="$ev" $checked> Add this property</label>]);
            $app->http->send_response_body_as_text
                (qq[<td><ins><code>$ev</code></ins>]);
          }
        }
      }

      $app->http->send_response_body_as_text (qq[
      <tfoot>
  
      <tr>
      <td><label><input type=checkbox name=prop-old
          value="derived_from:digest:@{[htescape ($path->[0])]}">
      Add <code>derived_from</code> property (&lt;-)</label>
      <td><label><input type=checkbox name=prop-new
          value="derived_from:digest:@{[htescape ($digest)]}" checked>
      Add <code>derived_from</code> property (->)</label>

      <tr>
      <td><button type=submit name=prop-sync value=new-to-old>Add properties
      to this file</button>
      <td><button type=submit name=prop-sync value=old-to-new>Add properties
      to this file</button>

      <tr>
      <td><a href="../../$edigest_old/propedit.html">Edit</a>
      <td><a href="../../$edigest_new/propedit.html">Edit</a>
  
      </table>
      </form>

      </details>
      <nav>[<a href="../../$edigest_old/diff/$edigest_new.html"
          >Reverse</a>]</nav>]);
      $app->http->send_response_body_as_text (scalar get_html_navigation ('../../', $path->[0]));
      $app->http->close_response_body;
      return;
    } elsif ($path->[1] eq 'diff-sync' and $path->[2] =~ /\A[0-9a-f]+\z/) {
      # /{key}/diff-sync/{key}
      if ($app->http->request_method eq 'POST') {
        lock_start ();
        my $dir = $app->text_param ('prop-sync') // '';
        my $digest = $dir eq 'old-to-new' ? $path->[0] : $path->[2];
        my $prop = get_prop_hash ($digest);
        delete_from_maps ($digest, $prop);
        for (@{$app->text_param_list
                   ($dir eq 'old-to-new' ? 'prop-new' : 'prop-old')}) {
          my ($n, $v) = split /\s*:\s*/, Encode::decode ('utf-8', $_), 2;
          my $lang = '';
          if ($n =~ s/\@([^@]*)$//) {
            $lang = $1;
          }
          add_prop ($prop, $n, $v, $lang);
        }
        set_prop_hash ($digest, $prop);
        update_maps ($digest, $prop);
        $app->set_status (204, reason_phrase => 'Properties updated');
        $app->http->close_response_body;
        commit_changes ();
        return;
      } else {
        return $app->send_error (405);
      }
    }
    
  } elsif (@$path == 1 and $path->[0] eq '') {
    # /
    if ($app->http->request_method eq 'POST') {
      lock_start ();
      my $s = $app->text_param ('s');
      my $uri = $app->text_param ('uri');
      my $ent;
      if (defined $s) {
        $ent->{digest} = $app->bare_param ('digest');
        if ((not defined $ent->{digest} or not length $ent->{digest}) and
            defined $uri) {
          my $containing_ent = get_remote_entity ($uri);
          $ent->{digest} = add_entity ($containing_ent);
        }
        $ent->{s} = $s; ## TODO: charset
        $ent->{charset} = 'utf-8';
        $ent->{documentation} = 'uri:'.$uri;
      } elsif (defined $uri) {
        $ent = get_remote_entity ($uri);
        $ent->{digest} = $app->bare_param ('digest');
      }

      if (defined $ent) {
        if (defined $ent->{s}) {
          my $digest = add_entity ($ent);
          $app->http->set_status (201);
          my $uri = $digest . q</prop.html>;
          $app->http->set_response_header (Location => $uri);
          my $euri = htescape ($uri);
          $app->http->send_response_body_as_text
              (qq[<a href="$euri">$euri</a>]);
          $app->http->close_response_body;
          commit_changes ();
          return;
        } else {
          $app->http->set_status (400);
          $app->http->set_response_header
              ('Content-Type' => 'text/plain; charset=utf-8');
          $app->http->send_response_body_as_text
              ("Specified URI Cannot Be Dereferenced\n");
          for my $key (sort {$a cmp $b} keys %$ent) {
            $app->http->send_response_body_as_text
                ($key . "\t" . $ent->{$key} . "\n");
          }
          $app->http->close_response_body;
          return;
        }
      } else {
        return $app->send_error (400, reason_phrase => 'No |uri|');
      }
    } else { # GET
      return $app->send_redirect ('/list/uri.html');
    }

  } elsif (@$path == 2 and $path->[0] eq 'list') {
    if ($path->[1] eq 'uri.html') {
      # /list/uri.html
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      
      my $query = $app->http->url->{query};
      my $prefix = '';
      
      if (defined $query and length $query) {
        $prefix = my $turi = percent_decode_c $query;
        my $eturi = htescape ($turi);
        
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with &lt;$eturi&gt;</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>Entries Associated with <code>&lt;$eturi&gt;</code></h1>
<ul>]);

        my $uri_to_entity = get_map ('uri_to_entity')->{$turi};
        for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
          my $uri2 = q<../> . $digest . q</prop.html>;
          my $euri2 = htescape ($uri2);
          my ($title_text, $title_lang) = get_title ($digest);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul><form action="../" method=post accept-charset=utf-8>
        <p><button type=submit>Retrieve latest entity</button>
        <input type=hidden name=uri value="$eturi"></p>
      </form>]);
      } else {
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of URIs</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>]);
      }
      
      $app->http->send_response_body_as_text (qq[<h1>List of URIs</h1><ul>]);
      
      my $lprefix = length $prefix;
      my $uri_list = get_map ('uri_to_entity');
      my $puri = '';
      for my $uri (sort {$a cmp $b}
                   grep {m!^(?:http://(?:web\.archive\.org/web|replay\.waybackmachine\.org)/[0-9]+/)?\Q$prefix\E!}
                   keys %$uri_list) {
        $uri =~ s!^((?:http://(?:web\.archive\.org/web|replay\.waybackmachine\.org)/[0-9]+/)?\Q$prefix\E.+?/+)[^/].*$!$1!;
        next if $uri eq $puri;
        $puri = $uri;
        my $euri = htescape ($uri);
        my $uri2 = q<uri.html?> . percent_encode_c $uri;
        my $euri2 = htescape ($uri2);
        $app->http->send_response_body_as_text (qq[<li><code class=uri lang=en>&lt;<a href="$euri2">$euri</a>&gt;</code></li>]);
      }
      $app->http->send_response_body_as_text (qq[</ul>]);
      
      $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
      $app->http->send_response_body_as_text (qq[</body></html>]);
      $app->http->close_response_body;
      return;

    } elsif ($path->[1] eq 'pubid.html') {
      # /list/pubid.html
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      my $query = $app->http->url->{query};
      if (defined $query and length $query) {
        my $turi = percent_decode_c $query;
        my $eturi = htescape ($turi);
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with "$eturi"</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>Entries Associated with <code>$eturi</code></h1>
<ul>]);

        my $uri_to_entity = get_map ('pubid_to_entity')->{$turi};
        for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
          my $uri2 = q<../> . $digest . q</prop.html>;
          my $euri2 = htescape ($uri2);
          my ($title_text, $title_lang) = get_title ($digest);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->send_response_body_as_text (qq[</body></html>]);
        $app->http->close_response_body;
        return;
      } else { # no query
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of Public Identifiers</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>List of Public Identifiers</h1>
<ul>]);

        my $uri_list = get_map ('pubid_to_entity');
        for (sort {$a cmp $b} keys %$uri_list) {
          my $euri = htescape ($_);
          my $uri2 = q<pubid.html?> . percent_encode_c $_;
          my $euri2 = htescape ($uri2);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2"><code lang=en class=public-id>$euri</code></a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->close_response_body;
        return;
      }

    } elsif ($path->[1] eq 'editor.html') {
      # /list/editor.html
      my $query = $app->http->url->{query};
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      if (defined $query and length $query) {
        my $turi = percent_decode_c $query;
        my $eturi = htescape ($turi);
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with $eturi</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>Entries Associated with $eturi</h1>
<ul>]);

        my $uri_to_entity = get_map ('editor_to_entity')->{$turi};
        for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
          my $uri2 = q<../> . $digest . q</prop.html>;
          my $euri2 = htescape ($uri2);
          my ($title_text, $title_lang) = get_title ($digest);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->close_response_body;
        return;
      } else { # no query
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of Editors/Authors</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>List of Editors/Authors</h1>
<ul>]);

        my $uri_list = get_map ('editor_to_entity');
        for (sort {$a cmp $b} keys %$uri_list) {
          my $euri = htescape ($_);
          my $uri2 = q<editor.html?> . percent_encode_c $_;
          my $euri2 = htescape ($uri2);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2">$euri</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->close_response_body;
        return;
      }

    } elsif ($path->[1] eq 'tag.html') {
      # /list/tag.html
      my $query = $app->http->url->{query};
      $app->http->set_response_header
          ('Content-Type' => 'text/html; charset=utf-8');
      if (defined $query and length $query) {
        my $turi = percent_decode_c $query;
        my $eturi = htescape ($turi);
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with "$eturi"</title>
<link rel=stylesheet href="/schema-style">
</head>
<body>
<h1>Entries Associated with <q>$eturi</q></h1>
<ul>]);

        my $uri_to_entity = get_map ('tag_to_entity')->{$turi};
        for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
          my $uri2 = q<../> . $digest . q</prop.html>;
          my $euri2 = htescape ($uri2);
          my ($title_text, $title_lang) = get_title ($digest);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->close_response_body;
        return;
      } else { # no query
        $app->http->send_response_body_as_text (qq[<!DOCTYPE HTML>
<html lang=en class=page-tags>
<head>
<title>List of Tags</title>
<link rel=stylesheet href="../../schema-style">
</head>
<body>
<h1>List of Tags</h1>
<ul>]);

        my $uri_list = get_map ('tag_to_entity');
        for (sort {$a cmp $b} keys %$uri_list) {
          my $euri = htescape ($_);
          my $uri2 = q<tag.html?> . percent_encode_c $_;
          my $euri2 = htescape ($uri2);
          $app->http->send_response_body_as_text (qq[<li><a href="$euri2">$euri</a></li>]);
        }
        $app->http->send_response_body_as_text (qq[</ul>]);
        $app->http->send_response_body_as_text (scalar get_html_navigation ('../', undef));
        $app->http->close_response_body;
        return;
      }
    }

  } elsif (@$path == 1 and $path->[0] eq 'schema-style') {
    # /schema-style
    my $f = file (__FILE__)->dir->file ('schema-style.css');
    $app->http->set_response_header
        ('Content-Type' => 'text/css; charset=utf-8');
    $app->http->set_response_last_modified ($f->stat->mtime);
    $app->http->send_response_body_as_ref (\scalar $f->slurp);
    $app->http->close_response_body;
    return;
  } elsif (@$path == 1 and $path->[0] eq 'schema-add') {
    # /schema-add
    my $f = file (__FILE__)->dir->file ('schema-add.en.html');
    $app->http->set_response_header
        ('Content-Type' => 'text/html; charset=utf-8');
    $app->http->set_response_last_modified ($f->stat->mtime);
    $app->http->send_response_body_as_ref (\scalar $f->slurp);
    $app->http->close_response_body;
    return;
  }

  return $app->throw_error (404);
} # main

sub htescape ($) {
  my $s = shift;
  $s =~ s/&/&amp;/g;
  $s =~ s/</&lt;/g;
  $s =~ s/>/&gt;/g;
  $s =~ s/"/&quot;/g;
  return $s;
} # htescape

sub get_digest ($) {
  require Digest::MD5;
  my $v = $_[0];
  $v =~ s/\x0D+\x0A/\x0A/g;
  $v =~ tr/\x0D/\x0A/;
  $v =~ s/\x0A+\z//;
  return Digest::MD5::md5_hex ($v);
} # get_digest

sub lock_start () {
  our $lock;
  open $lock, '>', $lock_file_name or die "$0: $lock_file_name: $!";
  use Fcntl ':flock';
  flock $lock, LOCK_EX;
} # lock_start

sub get_file_name ($) {
  return $data_directory . $_[0] . '.dat';
} # get_file_name

sub get_file_text ($) {
  my $file_name = get_file_name ($_[0]);
  if (-f $file_name) {
    open my $file, '<', $file_name or die "$0: $file_name: $!";
    binmode $file;
    local $/ = undef;
    return <$file>;
  } else {
    return undef;
  }
} # get_file_text

sub set_file_text ($$) {
  my $file_name = get_file_name ($_[0]);
  if (-f $file_name) {
    die "$0: $file_name: File exists";
  } else {
    open my $file, '>', $file_name or die "$0: $file_name: $!";
    binmode $file;
    print $file $_[1];
    close $file;
  }
} # set_file_text

sub get_prop_text ($) {
  my $file_name = $data_directory . $_[0] . '.prop';
  if (-f $file_name) {
    open my $file, '<:utf8', $file_name or die "$0: $file_name: $!";
    local $/ = undef;
    return <$file>;
  } else {
    return undef;
  }
} # get_prop_text

sub set_prop_text ($$;%) {
  my %opt = @_[2,$#$_];

  my $file_name = $data_directory . $_[0] . '.prop';
  unless ($opt{new_file}) {
    return 0 unless -f $file_name;
  }

  open my $file, '>:utf8', $file_name or die "$0: $file_name: $!";
  print $file $_[1];
  return 1;
} # set_prop_text

sub get_prop_hash ($) {
  my $prop_text = get_prop_text ($_[0]);
  my $r = {};
  for (split /\x0D?\x0A/, $prop_text) {
    if (/:/) {
      my ($n, $v) = split /\s*:\s*/, $_, 2;
      my $lang = '';
      if ($n =~ s/\@([^@]*)$//) {
        $lang = $1;
      }
      $v =~ s/\\n;/\x0A/g;
      $v =~ s/\\\\;/\\/g;
      push @{$r->{$n} ||= []}, [$v, $lang];
    } elsif (length $_) {
      push @{$r->{$_} ||= []}, ['', ''];
    }
  }
  return $r;
} # get_prop_hash

sub serialize_prop_hash ($) {
  my $hash = $_[0];
  my $r = '';
  for my $n (sort {$a cmp $b} keys %$hash) {
    my $key = $n;
    my @values = @{$hash->{$key}};
    @values = sort {$a->[0] cmp $b->[0]} @values
        if {
            ref => 1,
            tag => 1,
            uri => 1,
            ## NOTE: Following property names are intentionally
            ## excluded: |base_uri|, |content_type|, |charset|
           }->{$key};
    for (@values) {
      $n =~ tr/\x0D\x0A//d;
      my $lang = $_->[1];
      $lang =~ tr/\x0D\x0A//d;
      my $v = $_->[0];
      $v =~ s/\\/\\\\;/g;
      $v =~ s/\x0D?\x0A/\\n;/g;
      $v =~ s/\x0D/\\n;/g;
      $r .= $n . '@' . $lang . ':' . $v . "\x0A";
    }
  }
  return $r;
} # serialize_prop_hash

sub set_prop_hash ($$) {
  my $r = serialize_prop_hash ($_[1]);
  return set_prop_text ($_[0] => $r, new_file => 1);
} # set_prop_hash

sub get_normalized_prop_text ($) {
  my $prop_hash = get_prop_hash ($_[0]);
  return serialize_prop_hash ($prop_hash);
} # get_normalized_prop_text

sub get_title ($) {
  my $digest = shift;
  my $digest_to_title = get_map ('digest_to_title');
  my $v = $digest_to_title->{$digest};
  if (defined $v) {
    return @$v;
  } else {
    return ($digest, '');
  }
} # get_title

sub get_title_prop_text ($) {
  my $prop = shift;
  if ($prop->{label}->[0]) {
    return @{$prop->{label}->[0]};
  } elsif ($prop->{title}->[0]) {
    return @{$prop->{title}->[0]};
  } elsif ($prop->{file_name}->[0]) {
    return @{$prop->{file_name}->[0]};
  } elsif ($prop->{public_id}->[0]) {
    return @{$prop->{public_id}->[0]};
  } elsif ($prop->{system_id}->[0]) {
    return @{$prop->{system_id}->[0]};
  } elsif ($prop->{uri}->[0]) {
    my ($v, $l) = @{$prop->{uri}->[0]};
    $v =~ s/<>.*$//s;
    return ($v, $l);
  } else {
    return ('', '');
  }
} # get_title_prop_text

sub add_prop ($$$$) {
  my ($prop, $key) = ($_[0], $_[1]);
  $prop->{$key} ||= [];
  for (@{$prop->{$key}}) {
    if ($_->[0] eq $_[2] and $_->[1] eq $_[3]) {
      return;
    }
  }
  push @{$prop->{$key}}, [$_[2], $_[3]];
} # add_prop

use Storable qw/retrieve store/;

sub get_map ($) {
  my $file_name = $map_directory . $_[0] . '.smap';
  if (-f $file_name) {
    return retrieve ($file_name) or die "$0: $file_name: $!";
  } else {
    return {};  
  }
} # get_map

sub set_map ($$) {
  my $file_name = $map_directory . $_[0] . '.smap';
  store ($_[1] => $file_name) or die "$0: $file_name: $!";
  return 1;
} # set_map

sub delete_from_maps ($$) {
  my ($digest, $prop) = @_;
  
  my $uri_to_entity = get_map ('uri_to_entity');
  for (map {$_->[0]} @{$prop->{uri}}, @{$prop->{system_id}}) {
    my $uri = $_;
    $uri =~ s/<>.*$//gs;
    delete $uri_to_entity->{$uri}->{$digest};
  }
  set_map (uri_to_entity => $uri_to_entity);

  my $pubid_to_entity = get_map ('pubid_to_entity');
  for (map {$_->[0]} @{$prop->{public_id}}) {
    my $pubid = $_;
    ## TODO: Is this normalization correct?
    $pubid =~ s/\s+/ /g;
    $pubid =~ s/^ //;
    $pubid =~ s/ $//;
    delete $pubid_to_entity->{$pubid}->{$digest};
    delete $pubid_to_entity->{$pubid} unless keys %{$pubid_to_entity->{$pubid}};
  }
  set_map (pubid_to_entity => $pubid_to_entity);

  my $editor_to_entity = get_map ('editor_to_entity');
  for (map {$_->[0]} @{$prop->{editor}},
       @{$prop->{editor_mail}},
       @{$prop->{rcs_user}},
       @{$prop->{author}},
       @{$prop->{author_mail}}) {
    my $name = $_;
    $name =~ s/\s+/ /g;
    $name =~ s/^ //;
    $name =~ s/ $//;
    delete $editor_to_entity->{$name}->{$digest};
    delete $editor_to_entity->{$name} unless keys %{$editor_to_entity->{$name}};
  }
  set_map (editor_to_entity => $editor_to_entity);

  my $tag_to_entity = get_map ('tag_to_entity');
  for (map {$_->[0]} @{$prop->{tag}}) {
    my $name = $_;
    $name =~ s/\s+/ /g;
    $name =~ s/^ //;
    $name =~ s/ $//;
    delete $tag_to_entity->{$name}->{$digest};
    delete $tag_to_entity->{$name} unless keys %{$tag_to_entity->{$name}};
  }
  set_map (tag_to_entity => $tag_to_entity);

  #get_map ('digest_to_title');
} # delete_from_maps

sub update_maps ($$) {
  my ($digest, $prop) = @_;
  
  my $uri_to_entity = get_map ('uri_to_entity');
  for (map {$_->[0]} @{$prop->{uri}}, @{$prop->{system_id}}) {
    my $uri = $_;
    $uri =~ s/<>.*$//gs;
    $uri_to_entity->{$uri}->{$digest} = 1;
  }
  set_map (uri_to_entity => $uri_to_entity);

  my $pubid_to_entity = get_map ('pubid_to_entity');
  for (map {$_->[0]} @{$prop->{public_id}}) {
    my $pubid = $_;
    ## TODO: Is this normalization correct?
    $pubid =~ s/\s+/ /g;
    $pubid =~ s/^ //;
    $pubid =~ s/ $//;
    $pubid_to_entity->{$pubid}->{$digest} = 1;
  }
  set_map (pubid_to_entity => $pubid_to_entity);

  my $editor_to_entity = get_map ('editor_to_entity');
  for (map {$_->[0]} @{$prop->{editor}},
       @{$prop->{editor_mail}},
       @{$prop->{rcs_user}},
       @{$prop->{author}},
       @{$prop->{author_mail}}) {
    my $name = $_;
    $name =~ s/\s+/ /g;
    $name =~ s/^ //;
    $name =~ s/ $//;
    $editor_to_entity->{$name}->{$digest} = 1;
  }
  set_map (editor_to_entity => $editor_to_entity);

  my $tag_to_entity = get_map ('tag_to_entity');
  for (map {$_->[0]} @{$prop->{tag}}) {
    my $name = $_;
    $name =~ s/\s+/ /g;
    $name =~ s/^ //;
    $name =~ s/ $//;
    $tag_to_entity->{$name}->{$digest} = 1;
  }
  set_map (tag_to_entity => $tag_to_entity);

  my ($title_text, $title_lang) = get_title_prop_text ($prop);
  if ($title_text eq '' and $title_lang eq '') {
    $title_text = $digest;
  }
  my $digest_to_title = get_map ('digest_to_title');
  $digest_to_title->{$digest} = [$title_text, $title_lang];
  set_map (digest_to_title => $digest_to_title);
} # update_maps

sub commit_changes () {
  chdir $data_directory;

  system 'git add * > /dev/null';
  system 'git commit -m update -a > /dev/null';

  chdir $data_directory_back;
} # commit_changes

sub time_to_rfc3339 ($) {
  my @t = gmtime $_[0];
  return sprintf '%04d-%02d-%02d %02d:%02d:%02dZ',
      $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0];
} # time_to_rfc3339

sub http_to_rfc3339 ($) {
  if ($_[0] =~ /(\d+)\s*([A-Za-z]+)\s*(\d+)\s*(\d+):(\d+)(?>:(\d+))?\s*GMT/) {
    require Time::Local;
    my $t = Time::Local::timegm_nocheck
        ($6 || 0, $5, $4, $1,
         {jan => 0, feb => 1, mar => 2, apr => 3, may => 4,
          jun => 5, jul => 6, aug => 7, sep => 8, oct => 9,
          nov => 10, dec => 11}->{lc $2} || 0, $3);
    my @t = gmtime $t;
    return sprintf '%04d-%02d-%02d %02d:%02d:%02dZ',
        $t[5] + 1900, $t[4] + 1, $t[3], $t[2], $t[1], $t[0];
  } else {
    return '';
  }
} # http_to_rfc3339

sub rfc3339_to_http ($) {
  if ($_[0] =~ /\A(\d+)-(\d+)-(\d+)[Tt ](\d+):(\d+)(?>:(\d+)(?>\.\d+)?)?(?>Z|([+-]\d+):(\d+))\z/) {
    require Time::Local;
    my $t = Time::Local::timegm_nocheck
        ($6 || 0, $5 - $8, $4 - $7, $3, $2 - 1, $1);
    my @t = gmtime $t;
    return sprintf '%02d %s %04d %02d:%02d:%02d GMT',
        $t[3], [qw(Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec)]->[$t[4]],
        $t[5] + 1900, $t[2], $t[1], $t[0];
  } else {
    return '';
  }
} # rfc3339_to_http

sub get_html_navigation ($$) {
  my ($goto_base, $digest) = @_;
  my $r = qq[<div class=navigation>
[List files by <a href="${goto_base}list/uri.html">URI</a>,
<a href="${goto_base}list/pubid.html">Public ID</a>,
<a href="${goto_base}list/editor.html">Editor</a>,
<a href="${goto_base}list/tag.html">Tag</a>]
[<a href="${goto_base}../schema-add">Add file</a>]
];
  if (defined $digest) {
    $r .= qq[
[<a href="${goto_base}$digest/prop.html">Information</a>
(<a href="${goto_base}$digest/propedit.html">Edit</a>)]
[Cache (<a href="${goto_base}$digest/cache.html">annotated</a>, 
<a href="${goto_base}$digest/cache.dat">original</a>)]
[<button type=button onclick="
  var difffrom = '$digest';
  for (var i = 0; i < cookie.length; i++) {
    var v = cookie[i].split (/=/, 2);
    if (v[0] == 'difffrom') {
      difffrom = v[1];
      break;
    }
  }
  document.cookie = 'difffrom=' + difffrom +
      '; path=/; expires=' + (new Date (0)).toGMTString ();
  document.cookie = 'difffrom=$digest; path=/';
">Select for diff</button>
<button type=button onclick="
  var cookie = document.cookie.split (/\\s*;\\s*/);
  var difffrom = '$digest';
  for (var i = 0; i < cookie.length; i++) {
    var v = cookie[i].split (/=/, 2);
    if (v[0] == 'difffrom') {
      difffrom = v[1];
      break;
    }
  }
  location.href = '${goto_base}$digest/diff/' + difffrom + '.html';
">Generate diff</button>]
];
  }

  $r .= qq[</div>];

  return $r;
} # get_html_navigation

sub add_entity ($) {
  my $ent = shift;
  my $digest = get_digest ($ent->{s});
  my $prop = get_prop_hash ($digest);
  unless (keys %$prop) {
    ## New file
    set_file_text ($digest => $ent->{s});
  } else {
    delete_from_maps ($digest, $prop);
  }
  if (defined $ent->{uri} and $ent->{uri} !~ m!suika\.fam\.cx/~wakaba/-temp/!) {
    add_prop ($prop, 'uri', $ent->{uri}.'<>'.time_to_rfc3339 (time), '');
    add_prop ($prop, 'base_uri', $ent->{base_uri}, '')
        if defined $ent->{base_uri};
  }
  if (defined $ent->{digest} and length $ent->{digest}) {
    add_prop ($prop, 'src', 'digest:'.$ent->{digest}, '');
  }
  for my $prop_name (qw/documentation file_name charset last_modified/) {
    add_prop ($prop, $prop_name, $ent->{$prop_name}, '')
        if defined $ent->{$prop_name};
  }
  add_prop ($prop, 'content_type', $ent->{media_type}, '')
      if defined $ent->{media_type};
  for (@{$ent->{header_field} or []}) {
    my ($n, $v) = (lc $_->[0], $_->[1]);
    if ($n eq 'last-modified') {
      my $lm = http_to_rfc3339 ($v);
      if (length $lm) {
        add_prop ($prop, 'last_modified', $lm, '');
      }
    }
  }

  set_prop_hash ($digest => $prop);
  update_maps ($digest, $prop);
  return $digest;
} # add_entity

sub get_remote_entity ($) {
  my $r = {};
  my $request_uri = url_to_canon_url $_[0], 'about:blank';
  unless ($request_uri =~ m{^(?:https?|ftp):}) {
    return {uri => $request_uri,
            request_uri => $request_uri,
            error_status_text => 'URI scheme not allowed'};
  }

    require LWP::UserAgent;
    my $ua = WDCC::LWPUA->new (timeout => 30);
    $ua->agent ('Mozilla'); ## TODO: for now.
    $ua->parse_head (0);
    $ua->protocols_allowed ([qw/ftp http https/]);
    #$ua->max_size (1000_000);
    my $req = HTTP::Request->new (GET => $request_uri);
    my $res = $ua->request ($req);
    ## TODO: 401 sets |is_success| true.
    if ($res->is_success) {
      $r->{base_uri} = $res->base; ## NOTE: It does check |Content-Base|, |Content-Location|, and <base>. ## TODO: Use our own code!
      $r->{uri} = $res->request->uri;
      $r->{request_uri} = $request_uri;

      ## TODO: More strict parsing...
      my $ct = $res->header ('Content-Type');
      if (defined $ct and $ct =~ m#^([0-9A-Za-z._+-]+/[0-9A-Za-z._+-]+)#) {
        $r->{media_type} = lc $1;
      }
      if (defined $ct and $ct =~ /;\s*charset\s*=\s*"?(\S+)"?/i) {
        $r->{charset} = lc $1;
        $r->{charset} =~ tr/\\//d;
      }

      $r->{s} = ''.$res->content;
    } else {
      $r->{uri} = $res->request->uri;
      $r->{request_uri} = $request_uri;
      $r->{error_status_text} = $res->status_line;
    }

    $r->{header_field} = [];
    $res->scan (sub {
      push @{$r->{header_field}}, [$_[0], $_[1]];
    });
    $r->{header_status_code} = $res->code;
    $r->{header_status_text} = $res->message;

  return $r;
} # get_remote_entity

package WDCC::LWPUA;
BEGIN { push our @ISA, 'LWP::UserAgent'; }

sub redirect_ok {
  my $ua = shift;
  unless ($ua->SUPER::redirect_ok (@_)) {
    return 0;
  }

  my $uris = $_[1]->header ('Location');
  return 0 unless $uris;
  return 0 unless $uris =~ m{^(?:https|ftp):}i;
  return 1;
} # redirect_ok
