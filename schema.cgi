#!/usr/bin/perl
use strict;

use lib qw[/home/httpd/html/www/markup/html/whatpm
           /home/wakaba/work/manakai2/lib];
use CGI::Carp qw[fatalsToBrowser];
require Message::CGI::Carp;

my $data_directory = './data/';
my $map_directory = $data_directory;
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
      ## TODO: CONTENT_TYPE check
      my $prop_text = Encode::decode ('utf8', $cgi->entity_body);
      if (set_prop_text ($path[1], $prop_text, new_file => 0)) {
        my $prop = get_prop_hash ($path[1]);
        update_maps ($path[1] => $prop);

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
<title lang="$title_lang">$title_text &mdash; Information</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1 lang="$title_lang">$title_text &mdash; Information</h1>
];

      my %keys = map {$_ => 1} keys %$prop;

      print qq[<dl>];

      if ($prop->{uri}->[0]) {
        print qq[<dt lang="en">URI</dt>];
        for my $v (@{$prop->{uri}}) {
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
        for my $v (@{$prop->{public_id}}) {
          my $uri = $dom->create_uri_reference (q<../list/pubid.html>);
          $uri->uri_query ($v->[0]);
          my $elang = htescape ($v->[1]);
          print qq[<dd><a href="@{[htescape ($uri->get_uri_reference->uri_reference)]}"><code lang="@{[htescape ($v->[1])]}" class=public-id>@{[htescape ($v->[0])]}</code></a></dd>];
        }
        delete $keys{public_id};
      }

      if ($prop->{system_id}->[0]) {
        print qq[<dt lang="en">System Identifier</dt>];
        for my $v (@{$prop->{system_id}}) {
          my $uri = $v->[0];
          my $euri = htescape ($uri);
          my $elang = htescape ($v->[1]);
          print qq[<dd><code class=uri lang="$elang">&lt;<a href="$euri">$euri</a>&gt;</code>];
          
          my $uri2 = $dom->create_uri_reference (q<../list/uri.html>);
          $uri2->uri_query ($uri);
          print qq[ [<a href="@{[htescape ($uri2->get_uri_reference->uri_reference)]}" lang="en">more</a>]];
          
          print qq[</dd>];
        }
        delete $keys{system_id};
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

      for ([src => 'Source'], [ref => 'Reference'],
           [derived_from => 'Derived from']) {
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
              if ($n =~ s/\@([^@]+)//) {
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
      
      print qq[</dl>], get_html_navigation ('../', $path[1]);
      print qq[</body></html>];
      exit;
    }
  } elsif ($path[2] eq 'propedit.html') {
    print 'Location: ' . $cgi->script_name . "/../prop-edit\n\n";
    exit;
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
      my $prop = get_prop_hash ($path[1]);
      for my $v (@{$prop->{an} or []}) {
        if ($v->[0] =~ /^\Q$id\E(?>$|\t)/) {
          ## TODO: Check CONTENT_TYPE
          $v->[0] = Encode::decode ('utf8', $cgi->entity_body);
          set_prop_hash ($path[1], $prop);
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
      my $prop = get_prop_hash ($path[1]);
      for my $i (0..$#{$prop->{an} or []}) {
        my $v = $prop->{an}->[$i];
        if ($v->[0] =~ /^\Q$path[3]\E(?>$|\t)/) {
          splice @{$prop->{an}}, $i, 1, ();
          set_prop_hash ($path[1], $prop);
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
    print qq[</code></pre>];
    print '', get_html_navigation ('../../', $path[1]);
    print qq[</body></html>];
    exit;
  }
} elsif (@path == 2 and $path[0] eq '' and $path[1] eq '') {
  if ($cgi->request_method eq 'POST') {
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
      $ent->{documentation_uri} = $uri;
    } elsif (defined $uri) {
      $ent = get_remote_entity ($uri);
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
      print "Content-Type: text/html; charset=utf-8\n";
    my $query = $cgi->query_string;
    
    if (defined $query and length $query) {
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
      print qq[</ul>];
      print '', get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    } else {
      print "Content-Type: text/html; charset=utf-8\n";
      binmode STDOUT, ':utf8';
      print "\n";
      print qq[<!DOCTYPE HTML>
<html lang=en>
<head>
<title>List of URIs</title>
<link rel=stylesheet href="/www/style/html/xhtml">
</head>
<body>
<h1>List of URIs</h1>
<ul>];

      my $uri_list = get_map ('uri_to_entity');
      for (sort {$a cmp $b} keys %$uri_list) {
        my $euri = htescape ($_);
        my $uri2 = $dom->create_uri_reference (q<uri.html>);
        $uri2->uri_query ($_);
        my $euri2 = htescape ($uri2);
        print qq[<li><code class=uri lang=en>&lt;<a href="$euri2">$euri</a>&gt;</code></li>];
      }
      print qq[</ul>], get_html_navigation ('../', undef);
      print qq[</body></html>];
      exit;
    }
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

sub get_file_text ($) {
  my $file_name = $data_directory . $_[0] . '.dat';
  if (-f $file_name) {
    open my $file, '<', $file_name or die "$0: $file_name: $!";
    local $/ = undef;
    return <$file>;
  } else {
    return undef;
  }
} # get_file_text

sub set_file_text ($$) {
  my $file_name = $data_directory . $_[0] . '.dat';
  if (-f $file_name) {
    die "$0: $file_name: File exists";
  } else {
    open my $file, '>', $file_name or die "$0: $file_name: $!";
    print $file $_[1];
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

sub set_prop_hash ($$) {
  my $hash = $_[1];
  my $r = '';
  for my $n (sort {$a cmp $b} keys %$hash) {
    my $key = $n;
    for (@{$hash->{$key}}) {
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
  return set_prop_text ($_[0] => $r, new_file => 1);
} # set_prop_hash

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

sub get_map ($) {
  my $file_name = $map_directory . $_[0] . '.map';
  if (-f $file_name) {
    return do $file_name;
  } else {
    return {};  
  }
} # get_map

sub set_map ($$) {
  my $file_name = $map_directory . $_[0] . '.map';
  require Data::Dumper;
  $Data::Dumper::Sortkeys = 1;
  open my $file, '>', $file_name or die "$0: $file_name: $!";
  print $file Data::Dumper::Dumper ($_[1]);
  return 1;
} # set_map

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

  my ($title_text, $title_lang) = get_title_prop_text ($prop);
  if ($title_text eq '' and $title_lang eq '') {
    $title_text = $digest;
  }
  my $digest_to_title = get_map ('digest_to_title');
  $digest_to_title->{$digest} = [$title_text, $title_lang];
  set_map (digest_to_title => $digest_to_title);
} # update_maps

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
         {jan => 0, feb => 1, mar => 1, apr => 1, may => 1,
          jun => 1, jul => 1, aug => 1, sep => 1, oct => 1,
          nov => 1, dec => 1}->{lc $2} || 0, $3);
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
<a href="${goto_base}list/editor.html">Editor</a>]
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
  var cookie = document.cookie.split (/\s*;\s*/);
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
  }
  if (defined $ent->{uri} and $ent->{uri} !~ m!suika\.fam\.cx/~wakaba/-temp/!) {
    add_prop ($prop, 'uri', $ent->{uri}.'<>'.time_to_rfc3339 (time), '');
    add_prop ($prop, 'base_uri', $ent->{base_uri}, '')
        if defined $ent->{base_uri};
  }
  if (defined $ent->{digest}) {
    add_prop ($prop, 'src', 'digest:'.$ent->{digest}, '');
  }
  add_prop ($prop, 'documentation_uri', $ent->{documentation_uri}, '')
      if defined $ent->{documentation_uri};
  add_prop ($prop, 'content_type', $ent->{media_type}, '')
      if defined $ent->{media_type};
  add_prop ($prop, 'charset', $ent->{charset}, '')
      if defined $ent->{charset};
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
  my $request_uri = $_[0];
  my $r = {};

    my $uri = $dom->create_uri_reference ($request_uri);
    unless ({
             http => 1,
            }->{lc $uri->uri_scheme}) {
      return {uri => $request_uri, request_uri => $request_uri,
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
      return {uri => $request_uri, request_uri => $request_uri,
              error_status_text => 'Connection to the host is forbidden'};
    }

    require LWP::UserAgent;
    my $ua = WDCC::LWPUA->new;
    $ua->{wdcc_dom} = $dom;
    $ua->{wdcc_host_permit} = $host_permit;
    $ua->agent ('Mozilla'); ## TODO: for now.
    $ua->parse_head (0);
    $ua->protocols_allowed ([qw/http/]);
    $ua->max_size (1000_000);
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
