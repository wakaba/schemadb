#!/usr/bin/perl
use strict;
#use warnings;
use Path::Class;
use lib glob file (__FILE__)->dir->subdir ('modules/*/lib');
use CGI::Carp qw[fatalsToBrowser];
require Message::CGI::Carp;

my $data_directory = './data/';
my $data_directory_back = '../';
my $map_directory = $data_directory;
my $lock_file_name = $data_directory . '.lock';
my $DEBUG = 1;

use Encode;

use Message::URI::URIReference;
my $dom = 'Message::DOM::DOMImplementation';

use Message::CGI::HTTP;
my $cgi = Message::CGI::HTTP->new;

print "Cache-Control: no-cache\n" if $DEBUG;

my $path = $cgi->path_info;
$path = '' unless defined $path;

my @path = split m#/#, percent_decode ($path), -1;

if (@path == 3 and $path[0] eq '' and $path[1] =~ /\A[0-9a-f]+\z/) {
  if ($path[2] eq 'cache.dat') {
    my $file_text = get_file_text ($path[1]);
    if (defined $file_text) {
      my $prop = get_prop_hash ($path[1]);
      print "Status: 203 Non-Authoritative Information\n";
      my $ct = $prop->{content_type}->[0]
          ? $prop->{content_type}->[0]->[0]
          : 'application/octet-stream';
      if ($prop->{charset}->[0]) {
        $ct .= '; charset="' . $prop->{charset}->[0]->[0] . '"';
      }
      $ct =~ s/[\x09\x0A\x0D]+/ /g;
      $ct =~ s/[^\x20-\x7E]+//g;
      print "Content-Type: $ct\n";
      my $file_name = $prop->{file_name}->[0]
          ? $prop->{file_name}->[0]->[0] : '';
      $file_name =~ s/[\x09\x0A\x0D]+/ /g;
      $file_name =~ s/[^\x20-\x7E]+//g;
      if (length $file_name) {
        $file_name =~ s/\\/\\\\/g;
        $file_name =~ s/"/\\"/g;
        print qq[Content-Disposition: inline; filename="$file_name"\n];
      }
      my $uri = $prop->{base_uri}->[0] ? $prop->{base_uri}->[0]->[0] : '';
      if (length $uri) {
        print q[Content-Location: ];
        print $dom->create_uri_reference ($uri)
            ->get_uri_reference->uri_reference;
        print "\n";
      }
      my $lm = $prop->{last_modified}->[0]
          ? rfc3339_to_http ($prop->{last_modified}->[0]->[0]) : '';
      if (length $lm) {
        print "Last-Modified: Mon, $lm\n";
        ## NOTE: Weekday is not a matter, since Apache rewrites it.
      }
      print "\n";
      print $file_text;
      exit;      
    }    
  } elsif ($path[2] eq 'cache.html') {
    my $file_text = get_file_text ($path[1]);
    if (defined $file_text) {
      my ($title_text, $title_lang) = get_title ($path[1]);
      $title_text = htescape ($title_text);
      $title_lang = htescape ($title_lang);

      print "Content-Type: text/html; charset=utf-8\n\n";
      binmode STDOUT, ':utf8';
      print qq[<!DOCTYPE HTML>
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

<pre><code>];
      my $i = 1;
      for (split /\x0D?\x0A/, $file_text) {
        print qq[<span class=line id=line-@{[$i++]}>], htescape ($_);
        print qq[</span>\n];
      }
      print qq[</code></pre>], get_html_navigation ('../', $path[1]);
      print qq[</body></html>];
      exit;      
    }    
  } elsif ($path[2] eq 'prop.txt') {
    if ($cgi->request_method eq 'PUT') {
      lock_start ();
      ## TODO: CONTENT_TYPE check
      my $old_prop = get_prop_hash ($path[1]);
      my $prop_text = Encode::decode ('utf8', $cgi->entity_body);
      if (set_prop_text ($path[1], $prop_text, new_file => 0)) {
        delete_from_maps ($path[1] => $old_prop);
        my $prop = get_prop_hash ($path[1]);
        update_maps ($path[1] => $prop);
        commit_changes ();

        print "Status: 201 Created\nContent-Type: text/plain\n\n201";
        ## TODO: Is this status code OK?
      }
    } else {
      my $prop_text = get_prop_text ($path[1]);
      if (defined $prop_text) {
        print "Content-Type: text/plain; charset=utf-8\n\n";
        binmode STDOUT, ':utf8';
        print $prop_text;
        exit;
      }
    }
  } elsif ($path[2] eq 'prop.html') {
    my $prop = get_prop_hash ($path[1]);
    if (keys %$prop) {
      print "Content-Type: text/html; charset=utf-8\n\n";
      binmode STDOUT, ':utf8';

      my ($title_text, $title_lang) = get_title ($path[1]);
      $title_text = htescape ($title_text);
      $title_lang = htescape ($title_lang);

      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title lang="$title_lang">Information on $title_text</title>
<link rel=stylesheet href="../../schema-style">
</head>
<body>
<h1 lang="$title_lang">Information on $title_text</h1>
];

      my %keys = map {$_ => 1} keys %$prop;

      print qq[<dl>];

      if ($prop->{uri}->[0]) {
        print qq[<dt lang="en">URI</dt>];
        for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{uri}}) {
          my $uri = $v->[0];
          my $etime = '';
          if ($uri =~ s/<>(.*)$//s) {
            $etime = htescape ($1);
          }
          my $euri = htescape ($uri);
          my $elang = htescape ($v->[1]);
          print qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">$euri</a>&gt;</code>];
          
          my $uri2 = $dom->create_uri_reference (q<../list/uri.html>);
          $uri2->uri_query ($uri);
          print qq[ [<a href="@{[htescape ($uri2->get_uri_reference->uri_reference)]}" lang="en">more</a>]];
          
          if (length $etime) {
            print qq[ (<time>$etime</time>)];
          }
          print qq[</dd>];
        }
        delete $keys{uri};
      }

      if ($prop->{public_id}->[0]) {
        print qq[<dt lang="en">Public Identifier</dt>];
        for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{public_id}}) {
          my $uri = $dom->create_uri_reference (q<../list/pubid.html>);
          $uri->uri_query ($v->[0]);
          my $elang = htescape ($v->[1]);
          print qq[<dd><a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}"><code lang="@{[htescape ($v->[1])]}" class=public-id>@{[htescape ($v->[0])]}</code></a></dd>];
        }
        delete $keys{public_id};
      }

      if ($prop->{system_id}->[0]) {
        print qq[<dt lang="en">System Identifier</dt>];
        for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{system_id}}) {
          my $uri = $v->[0];
          if (defined $prop->{base_uri}->[0]) {
            $uri = $dom->create_uri_reference ($uri)
                ->get_absolute_reference
                    ($prop->{base_uri}->[0]->[0])->uri_reference;
          }
          my $euri = htescape ($uri);
          my $elang = htescape ($v->[1]);
          print qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">@{[htescape ($v->[0])]}</a>&gt;</code>];
          
          my $uri2 = $dom->create_uri_reference (q<../list/uri.html>);
          $uri2->uri_query ($uri);
          print qq[ [<a href="@{[htescape ($uri2->get_uri_reference->uri_reference)]}" lang="en">more</a>]];
          
          print qq[</dd>];
        }
        delete $keys{system_id};
      }

      for ([tag => 'Tag']) {
        my $key = $_->[0];
        my $label = $_->[1];
        if ($prop->{$key}) {
          print qq[<dt lang="en" class="$key">$label</dt>];
          for my $v (sort {$a->[0] cmp $b->[0]} @{$prop->{$key}}) {
            my $uri = $dom->create_uri_reference (q<../list/tag.html>);
            $uri->uri_query ($v->[0]);
            my $elang = htescape ($v->[1]);
            print qq[<dd class="$key"><a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}" lang="@{[htescape ($v->[1])]}">@{[htescape ($v->[0])]}</a></dd>];
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
          print qq[<dt lang="en">$label</dt>];
          for my $v (@{$prop->{$key}}) {
            my $uri = $dom->create_uri_reference (q<../list/editor.html>);
            $uri->uri_query ($v->[0]);
            my $elang = htescape ($v->[1]);
            print qq[<dd><a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}" lang="@{[htescape ($v->[1])]}">@{[htescape ($v->[0])]}</a></dd>];
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
          print qq[<dt>], $label, q[</dt>];
          for (@{$prop->{$key}}) {
            my $v = $_->[0];
            print qq[<dd><dl>];
            for (split /\s*;\s*/, $v) {
              my ($n, $v) = split /\s*:\s*/, $_, 2;
              my $l = '';
              if ($n =~ s/\@([^@]*)$//) {
                $l = $1;
              }
              if ($n eq 'public_id') {
                print qq[<dt>Public Identifier</dt><dd>];
                my $uri = $dom->create_uri_reference (q<../list/pubid.html>);
                $uri->uri_query ($v);
                print qq[<a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}"><code class=public-id lang="@{[htescape ($l)]}">@{[htescape ($v)]}</code></a></dd>];
              } elsif ($n eq 'system_id' or $n eq 'uri') {
                print qq[<dt>];
                print {system_id => 'System Identifier',
                       uri => 'URI'}->{$n};
                print qq[</dt><dd>];
                my $v_uri = $dom->create_uri_reference ($v);
                if (defined $prop->{base_uri}->[0]) {
                  $v_uri = $v_uri->get_absolute_reference
                      ($prop->{base_uri}->[0]->[0]);
                }
                my $uri = $dom->create_uri_reference (q<../list/uri.html>);
                $uri->uri_query ($v_uri->uri_reference);
                print qq[<code class=uri lang="@{[htescape ($l)]}">&lt;<a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}">@{[htescape ($v)]}</a>&gt;</code></dd>];
              } elsif ($n eq 'digest') {
                print qq[<dt>File</dt><dd>];
                my ($title_text, $title_lang) = get_title ($v);
                my $uri = $dom->create_uri_reference (q<../> . $v . q</prop.html>);
                print qq[<a lang="@{[htescape ($title_lang)]}" href="@{[htescape ($uri->get_uri_reference->uri_reference)]}">@{[htescape ($title_text)]}</a>];
                print qq[ [<a href="diff/@{[htescape ($v)]}.html">Diff</a>]];
                print qq[</dd>];
              } else {
                print qq[<dt>], htescape ($n), qq[</dt>];
                print qq[<dd lang="@{[htescape ($l)]}">], htescape ($v);
                print qq[</dd>];
              }
            }
            print qq[</dl></dd>];
          }
          delete $keys{$key};
        }
      }

      for my $key (sort {$a cmp $b} keys %keys) {
        next unless @{$prop->{$key}};
        print qq[<dt>], htescape ($key), qq[</dt>];
        for (@{$prop->{$key}}) {
          print qq[<dd lang="@{[htescape ($_->[1])]}">],
              htescape ($_->[0]), qq[</dd>\n];
        }
      }

      print qq[<dt>MD5 Digest</dt><dd><code>$path[1]</code></dd>\n];
      print qq[</dl>];

      if (defined $prop->{content_type}->[0] and
          ($prop->{content_type}->[0]->[0] eq 'application/zip' or
           $prop->{content_type}->[0]->[0] =~ /\+zip$/)) {
        print q[<form action=expand method=post><p><button type=submit>Expand</button></p></form>];
      }

      print scalar get_html_navigation ('../', $path[1]);
      print qq[</body></html>];
      exit;
    }
  } elsif ($path[2] eq 'propedit.html') {
    print 'Location: ' . $cgi->script_name . "/../prop-edit\n\n";
    exit;
  } elsif ($path[2] eq 'expand') {
    if ($cgi->request_method eq 'POST') {
      lock_start ();
      my $prop = get_prop_hash ($path[1]);
      if (defined $prop->{content_type}->[0] and
          ($prop->{content_type}->[0]->[0] eq 'application/zip' or
           $prop->{content_type}->[0]->[0] =~ /\+zip$/)) {
        my $prop = get_prop_hash ($path[1]);
        my $file_name = get_file_name ($path[1]);
        require Archive::Zip;
        my $zip = Archive::Zip->new;
        my $error_code = $zip->read($file_name);
        if ($error_code == Archive::Zip::AZ_OK ()) {
          print "Status: 201 Created\nContent-Type: text/html; charset=utf-8\n\n";
          $| = 1;
          print qq[<!DOCTYPE HTML><html lang=""><title>201 Created</title><ul>];
          for my $member ($zip->members) {
            next if $member->isDirectory;
            my $ent = {};
            $ent->{file_name} = $member->fileName;
            $ent->{last_modified} = time_to_rfc3339 ($member->lastModTime);
            $ent->{digest} = $path[1];
            $ent->{s} = $member->contents;
            my $digest = add_entity ($ent);
            my $uri = '../'.$digest.q</prop.html>;
            print qq[<li><a href="@{[htescape ($uri)]}"><code class=file>@{[htescape ($ent->{file_name})]}</code></a></li>];
            add_prop ($prop, 'contains', 'digest:'.$digest, '');
          }
          print qq[</ul>];
          set_prop_hash ($path[1], $prop);
          commit_changes ();
          exit;
        } else {
          print "Status: 400 Not expandable\nContent-Type: text/plain\n\n400 ($error_code)";
          exit;
        }
      } else {
        print "Status: 400 Not expandable\nContent-Type: text/plain\n\n400";
        exit;
      }
    } else {
      print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
      exit;
    }
  } elsif ($path[2] eq 'annotation.txt') {
    if ($cgi->request_method eq 'POST') {
      print "Content-Type: text/plain; charset=us-ascii\n\n";
      print time . (int (rand (10)), int (rand (10)), int (rand (10)));
      exit;
    } else {
      my $prop = get_prop_hash ($path[1]);
      print "Content-Type: text/plain; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      for (@{$prop->{an} or []}) {
        print $_->[0], "\n";
      }
      exit;
    }
  }
} elsif (@path == 4 and $path[0] eq '' and $path[1] =~ /\A[0-9a-f]+\z/) {
  if ($path[2] eq 'annotation' and $path[3] =~ /\A([0-9A-Za-z]+)\.txt\z/) {
    my $id = $1;
    if ($cgi->request_method eq 'PUT') {
      lock_start ();
      my $prop = get_prop_hash ($path[1]);
      for my $v (@{$prop->{an} or []}) {
        if ($v->[0] =~ /^\Q$id\E(?>$|\t)/) {
          ## TODO: Check CONTENT_TYPE
          $v->[0] = Encode::decode ('utf8', $cgi->entity_body);
          set_prop_hash ($path[1], $prop);
          commit_changes ();
          print "Status: 201 Created\nContent-Type: text/plain\n\n201";
          exit; ## TODO: 201?
        }
      }
      push @{$prop->{an} ||= []},
          [Encode::decode ('utf8', $cgi->entity_body), ''];
      set_prop_hash ($path[1], $prop);
      print "Status: 201 Created\nContent-Type: text/plain\n\n201";
      exit;
    } else {
      print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
      exit;
    }
  } elsif ($path[2] eq 'annotation' and $path[3] =~ /\A[0-9A-Za-z]+\z/) {
    if ($cgi->request_method eq 'DELETE') {
      lock_start ();
      my $prop = get_prop_hash ($path[1]);
      for my $i (0..$#{$prop->{an} or []}) {
        my $v = $prop->{an}->[$i];
        if ($v->[0] =~ /^\Q$path[3]\E(?>$|\t)/) {
          splice @{$prop->{an}}, $i, 1, ();
          set_prop_hash ($path[1], $prop);
          commit_changes ();
          print "Status: 200 Deleted\nContent-Type: text/plain\n\n200";
          exit; ## TODO: 200?
        }
      }
      print "Status: 200 Deleted\nContent-Type: text/plain\n\n200";
      exit; ## TODO: 200
    } else {
      print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
      exit;
    }
  } elsif ($path[2] eq 'diff' and $path[3] =~ /\A([0-9a-f]+)\.html\z/) {
    my $digest = $1;
    ## TODO: charset
    my $from_text = [split /\x0D?\x0A/, get_file_text ($digest)];
    my $to_text = [split /\x0D?\x0A/, get_file_text ($path[1])];
    my $etitlea = htescape (get_title ($digest));
    my $etitleb = htescape (get_title ($path[1]));
    print "Content-Type: text/html; charset=utf-8\n\n";
    binmode STDOUT, ':utf8';
    $| = 1;
    print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Diff between "$etitlea" and "$etitleb"</title>
<link rel=stylesheet href="../../../schema-style">
</head>
<body>
<h1>Diff between 
<a href="../../@{[htescape ($digest)]}/prop.html"><cite>$etitlea</cite></a> and 
<a href="../prop.html"><cite>$etitleb</cite></a></h1>

<pre><code>];
    require Algorithm::Diff;
    my $diff = Algorithm::Diff->new ($from_text, $to_text);
    while ($diff->Next) {
      if ($diff->Same) {
        print qq[<span class=line>], htescape ($_), qq[</span>\n]
            for $diff->Items (1);
      } else {
        print qq[<del><span class=line>], htescape ($_), qq[</span></del>\n]
            for $diff->Items (1);
        print qq[<ins><span class=line>], htescape ($_), qq[</span></ins>\n]
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
    my $edigest_new = htescape ($path[1]);
    print qq[
      </code></pre>
      
      <details id=diff-props>
      <legend>Properties</legend>

      <form action="../diff-sync/$edigest_old" method=post
          accept-charset=utf-8>
      <table class=diff-props>
      <thead>
      <tr><th><a href="../../$edigest_old/prop.html"><cite>$etitlea</cite></a>
      <th><a href="../prop.html"><cite>$etitleb</cite></a>

      <tbody>];
    
    my $from_prop_text = [grep {length $_}
                          split /\x0D?\x0A/,
                          get_normalized_prop_text ($digest)];
    my $to_prop_text = [grep {length $_}
                        split /\x0D?\x0A/,
                        get_normalized_prop_text ($path[1])];
    my $diff = Algorithm::Diff->new ($from_prop_text, $to_prop_text);
    while ($diff->Next) {
      if ($diff->Same) {
        print qq[<tr><td colspan=2><code>], htescape ($_), q[</code>]
            for $diff->Items (1);
      } else {
        for ($diff->Items (1)) {
          my $ev = htescape ($_);
          print qq[<tr><td><del><code>$ev</code></del>];
          my $checked = $ev =~ /^(?:$no_sync_pattern)[\@:]/ ? '' : 'checked';
          print qq[<td><label><input type=checkbox name=prop-new value="$ev"
                   $checked> Add this property</label>];
        }
        for ($diff->Items (2)) {
          my $ev = htescape ($_);
          my $checked = $ev =~ /^(?:$no_sync_pattern)[\@:]/ ? '' : 'checked';
          print qq[<tr><td><label><input type=checkbox name=prop-old
                   value="$ev" $checked> Add this property</label>];
          print qq[<td><ins><code>$ev</code></ins>];
        }
      }
    }

    print qq[
      <tfoot>
  
      <tr>
      <td><label><input type=checkbox name=prop-old
          value="derived_from:digest:@{[htescape ($path[1])]}">
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
          >Reverse</a>]</nav>];
    print '', get_html_navigation ('../../', $path[1]);
    exit;
  } elsif ($path[2] eq 'diff-sync' and $path[3] =~ /\A[0-9a-f]+\z/) {
    if ($cgi->request_method eq 'POST') {
      lock_start ();
      my $dir = $cgi->get_parameter ('prop-sync') // '';
      my $digest = $dir eq 'old-to-new' ? $path[1] : $path[3];
      my $prop = get_prop_hash ($digest);
      delete_from_maps ($digest, $prop);
      for ($cgi->get_parameter
               ($dir eq 'old-to-new' ? 'prop-new' : 'prop-old')) {
        my ($n, $v) = split /\s*:\s*/, Encode::decode ('utf-8', $_), 2;
        my $lang = '';
        if ($n =~ s/\@([^@]*)$//) {
          $lang = $1;
        }
        add_prop ($prop, $n, $v, $lang);
      }
      set_prop_hash ($digest, $prop);
      update_maps ($digest, $prop);
      print "Status: 204 Properties Updated\n\n";
      commit_changes ();
      exit;
    } else {
      print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
      exit;
    }
  }
} elsif (@path == 2 and $path[0] eq '' and $path[1] eq '') {
  if ($cgi->request_method eq 'POST') {
    lock_start ();
    my $s = $cgi->get_parameter ('s');
    my $uri = $cgi->get_parameter ('uri');
    my $ent;
    if (defined $s) {
      $ent->{digest} = $cgi->get_parameter ('digest');
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
      $ent->{digest} = $cgi->get_parameter ('digest');
    }

    if (defined $ent) {
      if (defined $ent->{s}) {
        my $digest = add_entity ($ent);

        print "Status: 201 Created\n";
        print "Content-Type: text/html; charset=iso-8859-1\n";
        my $uri = $dom->create_uri_reference ($digest . q</prop.html>)
            ->get_absolute_reference ($cgi->request_uri)
            ->get_uri_reference
            ->uri_reference;
        print "Location: $uri\n";
        print "\n";
        my $euri = htescape ($uri);
        print qq[<a href="$euri">$euri</a>];
        commit_changes ();
        exit;
      } else {
        print "Status: 400 Specified URI cannot be dereferenced\n";
        print "Content-Type: text/plain; charset=iso-8859-1\n\n";
        print "Specified URI Cannot Be Dereferenced\n";
        print "~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n";
        for my $key (sort {$a cmp $b} keys %$ent) {
          print $key, "\t", $ent->{$key}, "\n";
        }
        exit;
      }
    } else {
      print "Status: 400 No uri Parameter Specified\n";
      print "Content-Type: text/plain\n\n400";
      exit;
    }
  } else {
    print "Status: 405 Method Not Allowed\nContent-Type: text/plain\n\n405";
    exit;
  }
} elsif (@path == 3 and $path[0] eq '' and $path[1] eq 'list') {
  if ($path[2] eq 'uri.html') {
    print "Content-Type: text/html; charset=utf-8\n\n";
    binmode STDOUT, ':utf8';
    $| = 1;
    
    my $query = $cgi->query_string;
    my $prefix = '';
    
    if (defined $query and length $query) {
      $query = '?' . $query;
      my $turi = $dom->create_uri_reference ($query)
          ->get_iri_reference
          ->uri_query;
      $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
      $prefix = $turi;
      my $eturi = htescape ($turi);
      
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with &lt;$eturi&gt;</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with <code>&lt;$eturi&gt;</code></h1>
<ul>];

      my $uri_to_entity = get_map ('uri_to_entity')->{$turi};
      for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
        my $uri2 = $dom->create_uri_reference
          (q<../> . $digest . q</prop.html>);
        my $euri2 = htescape ($uri2);
        my ($title_text, $title_lang) = get_title ($digest);
        print qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>];
      }
      print qq[</ul><form action="../" method=post accept-charset=utf-8>
        <p><button type=submit>Retrieve latest entity</button>
        <input type=hidden name=uri value="$eturi"></p>
      </form>];
    } else {
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of URIs</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>];
    }
    
    print qq[<h1>List of URIs</h1><ul>];
      
    my $lprefix = length $prefix;
    my $uri_list = get_map ('uri_to_entity');
    my $puri = '';
    for my $uri (sort {$a cmp $b} grep {$prefix eq substr $_, 0, $lprefix}
                 keys %$uri_list) {
      $uri =~ s!^(\Q$prefix\E.+?/+)[^/].*$!$1!;
      next if $uri eq $puri;
      $puri = $uri;
      my $euri = htescape ($uri);
      my $uri2 = $dom->create_uri_reference (q<uri.html>);
      $uri =~ s/([%\\\|<>`])/sprintf '%%%02X', ord $1/ge; # TODO: ...
      $uri2->uri_query ($uri);
      my $euri2 = htescape ($uri2);
      print qq[<li><code class=uri lang=en>&lt;<a href="$euri2">$euri</a>&gt;</code></li>];
    }
    print qq[</ul>];
   
    print scalar get_html_navigation ('../', undef);
    print qq[</body></html>];
    exit;
  } elsif ($path[2] eq 'pubid.html') {
    my $query = $cgi->query_string;
    
    if (defined $query and length $query) {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      
      $query = '?' . $query;
      my $turi = $dom->create_uri_reference ($query)
          ->get_iri_reference
          ->uri_query;
      $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
      my $eturi = htescape ($turi);
      
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with "$eturi"</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with <code>$eturi</code></h1>
<ul>];

      my $uri_to_entity = get_map ('pubid_to_entity')->{$turi};
      for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
        my $uri2 = $dom->create_uri_reference
            (q<../> . $digest . q</prop.html>);
        my $euri2 = htescape ($uri2);
        my ($title_text, $title_lang) = get_title ($digest);
        print qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    } else {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of Public Identifiers</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>List of Public Identifiers</h1>
<ul>];

      my $uri_list = get_map ('pubid_to_entity');
      for (sort {$a cmp $b} keys %$uri_list) {
        my $euri = htescape ($_);
        my $uri2 = $dom->create_uri_reference
            (q<pubid.html>);
        $uri2->uri_query ($_);
        my $euri2 = htescape ($uri2);
        print qq[<li><a href="$euri2"><code lang=en class=public-id>$euri</code></a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    }
  } elsif ($path[2] eq 'editor.html') {
    my $query = $cgi->query_string;
    
    if (defined $query and length $query) {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      
      $query = '?' . $query;
      my $turi = $dom->create_uri_reference ($query)
          ->get_iri_reference
          ->uri_query;
      $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
      my $eturi = htescape ($turi);
      
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with $eturi</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with $eturi</h1>
<ul>];

      my $uri_to_entity = get_map ('editor_to_entity')->{$turi};
      for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
        my $uri2 = $dom->create_uri_reference
            (q<../> . $digest . q</prop.html>);
        my $euri2 = htescape ($uri2);
        my ($title_text, $title_lang) = get_title ($digest);
        print qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    } else {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of Editors/Authors</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>List of Editors/Authors</h1>
<ul>];

      my $uri_list = get_map ('editor_to_entity');
      for (sort {$a cmp $b} keys %$uri_list) {
        my $euri = htescape ($_);
        my $uri2 = $dom->create_uri_reference (q<editor.html>);
        $uri2->uri_query ($_);
        my $euri2 = htescape ($uri2);
        print qq[<li><a href="$euri2">$euri</a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    }
  } elsif ($path[2] eq 'tag.html') {
    my $query = $cgi->query_string;
    
    if (defined $query and length $query) {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      
      $query = '?' . $query;
      my $turi = $dom->create_uri_reference ($query)
          ->get_iri_reference
          ->uri_query;
      $turi =~ s/%([0-9A-Fa-f]{2})/chr hex $1/ge;
      my $eturi = htescape ($turi);
      
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>Entries Associated with "$eturi"</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>Entries Associated with <q>$eturi</q></h1>
<ul>];

      my $uri_to_entity = get_map ('tag_to_entity')->{$turi};
      for my $digest (sort {$a cmp $b} keys %$uri_to_entity) {
        my $uri2 = $dom->create_uri_reference
            (q<../> . $digest . q</prop.html>);
        my $euri2 = htescape ($uri2);
        my ($title_text, $title_lang) = get_title ($digest);
        print qq[<li><a href="$euri2" lang="@{[htescape ($title_lang)]}">@{[htescape ($title_text)]}</a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    } else {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      print qq[<!DOCTYPE HTML>
<html lang=en class=page-tags>
<head>
<title>List of Tags</title>
<link rel=stylesheet href="../../schema-style">
</head>
<body>
<h1>List of Tags</h1>
<ul>];

      my $uri_list = get_map ('tag_to_entity');
      for (sort {$a cmp $b} keys %$uri_list) {
        my $euri = htescape ($_);
        my $uri2 = $dom->create_uri_reference (q<tag.html>);
        $uri2->uri_query ($_);
        my $euri2 = htescape ($uri2);
        print qq[<li><a href="$euri2">$euri</a></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    }
  }
}

print "Status: 404 Not Found\nContent-Type: text/plain\n\n404";
exit;

sub percent_decode ($) {
  return $dom->create_uri_reference ($_[0])
      ->get_iri_reference
      ->uri_reference;
} # percent_decode

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
  my $request_uri = $dom->create_uri_reference ($_[0]);
  $request_uri->uri_fragment (undef);
  my $r = {};

    my $uri = $dom->create_uri_reference ($request_uri);
    unless ({
             ftp => 1,
             http => 1,
             https => 1,
            }->{lc $uri->uri_scheme}) {
      return {uri => $request_uri->uri_reference,
              request_uri => $request_uri->uri_reference,
              error_status_text => 'URI scheme not allowed'};
    }

    require Message::Util::HostPermit;
    my $host_permit = new Message::Util::HostPermit;
    $host_permit->add_rule (<<EOH);
Allow host=suika port=80
Deny host=suika
Allow host=suika.fam.cx port=80
Deny host=suika.fam.cx
Deny host=localhost
Deny host=*.localdomain
Deny ipv4=0.0.0.0/8
Deny ipv4=10.0.0.0/8
Deny ipv4=127.0.0.0/8
Deny ipv4=169.254.0.0/16
Deny ipv4=172.0.0.0/11
Deny ipv4=192.0.2.0/24
Deny ipv4=192.88.99.0/24
Deny ipv4=192.168.0.0/16
Deny ipv4=198.18.0.0/15
Deny ipv4=224.0.0.0/4
Deny ipv4=255.255.255.255/32
Deny ipv6=0::0/0
Allow host=*
EOH
    unless ($host_permit->check ($uri->uri_host, $uri->uri_port || 80)) {
      return {uri => $request_uri->uri_reference,
              request_uri => $request_uri->uri_reference,
              error_status_text => 'Connection to the host is forbidden'};
    }

    require LWP::UserAgent;
    my $ua = WDCC::LWPUA->new (timeout => 30);
    $ua->{wdcc_dom} = $dom;
    $ua->{wdcc_host_permit} = $host_permit;
    $ua->agent ('Mozilla'); ## TODO: for now.
    $ua->parse_head (0);
    $ua->protocols_allowed ([qw/ftp http https/]);
    #$ua->max_size (1000_000);
    my $req = HTTP::Request->new (GET => $request_uri->uri_reference);
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
      $r->{request_uri} = $request_uri->uri_reference;
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
  my $uri = $ua->{wdcc_dom}->create_uri_reference ($uris);
  unless ({
           http => 1,
          }->{lc $uri->uri_scheme}) {
    return 0;
  }
  unless ($ua->{wdcc_host_permit}->check ($uri->uri_host, $uri->uri_port || 80)) {
    return 0;
  }
  return 1;
} # redirect_ok
